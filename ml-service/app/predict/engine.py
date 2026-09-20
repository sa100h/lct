"""Prediction engine: turns a feature vector into a forecast.

One horizon (>= 24 h by default). Risk score is clipped to [0, 1]; the
predicted label uses the per-category threshold from meta.json (default 0.5).

Feature sourcing (195/196 names for the LightGBM production models):
- The 184/185 base features come from the request's `current_features`
  (client-provided); missing keys default to 0.0.
- The 11 lag features are computed server-side from the LagStore's
  per-subject history (the same lag_features module train uses —
  train/serve parity). A lag key explicitly present in the request
  overrides the store value (client > server). A subject without
  history gets the documented NaN vector (LightGBM handles NaN natively).
- Engine-agnostic predict: lgb.Booster (model.lgb) via predict_proba()
  from app.models.lgbm_model; sklearn estimator (model.joblib) via
  predict_proba(X)[0, 1].
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.ingest.lag_features import LAG_SET
from app.models.registry import get_registry
from app.predict.lag_store import get_store
from app.schemas import Prediction


def is_booster(model: object) -> bool:
    """lgb.Booster (LightGBM artifact) vs sklearn estimator (HGB fallback)."""
    return type(model).__name__ == "Booster" or hasattr(model, "model_file")


class PredictEngine:
    def __init__(self) -> None:
        self._registry = get_registry()
        self._models: dict[str, object] = {}

    def _model(self, category: str) -> object:
        if category not in self._models:
            self._models[category] = self._registry.load(category)
        return self._models[category]

    def _probability(self, model: object, vector: list[float]) -> float:
        if is_booster(model):
            # LightGBM: Booster.predict on a 2-D row, native NaN handling.
            return float(np.asarray(model.predict(np.asarray([vector])), dtype=np.float64)[0])
        return float(model.predict_proba(np.asarray([vector], dtype=np.float64))[0, 1])

    def predict(
        self,
        category: str,
        subject_id: str,
        features: dict[str, float] | None,
        horizon_hours: int,
        as_of: datetime | None = None,
    ) -> Prediction:
        feature_names = self._registry.feature_names(category)
        if not feature_names:
            raise KeyError(f"No model features registered for category '{category}'")

        features = features or {}
        as_of = as_of or datetime.now(timezone.utc)

        # Server-side lags from the observation store (empty history -> NaN vector).
        lag_values = get_store().lags_for(category, subject_id, as_of)

        vector: list[float] = []
        named: dict[str, float] = {}
        for name in feature_names:
            if name in features and features[name] is not None:
                value = float(features[name])  # client overrides server-side lag
            else:
                value = lag_values.get(name, 0.0) if name in LAG_SET else 0.0
            named[name] = value
            vector.append(value)

        model = self._model(category)
        probability = self._probability(model, vector)
        probability = min(max(probability, 0.0), 1.0)

        state = self._registry.status(category)
        threshold = self._registry.threshold(category)
        return Prediction(
            category=category,  # type: ignore[arg-type]
            subject_id=subject_id,
            risk_score=probability,
            probability=probability,
            predicted_label=probability >= threshold,
            horizon_hours=horizon_hours,
            predicted_at=datetime.now(timezone.utc),
            model_version=state.model_version,
            feature_importance=named,
        )
