"""Prediction engine: turns a feature vector into a forecast.

One horizon (>= 24 h by default). Risk score is clipped to [0, 1]; the
predicted label uses the per-category threshold from meta.json (default 0.5).

Feature sourcing (195/196 names for the LightGBM production models):
- The 184/185 base features: request's `current_features` (client) first,
  then the subject's LATEST OBSERVED FEATURE ROW from the LagStore sidecar
  (auto-feature assembly — no manual vector needed), then 0.0.
- The 11 lag features are computed server-side from the LagStore's
  per-subject history (the same lag_features module train uses —
  train/serve parity). A lag key explicitly present in the request
  overrides the store value (client > server). A subject without
  history gets the documented NaN vector (LightGBM handles NaN natively).
  NOTE: the 11 lag columns of the latest store row are stale (that past
  day's lags) and are always replaced by freshly computed serve lags.
- Engine-agnostic predict: lgb.Booster (model.lgb) via predict_proba()
  from app.models.lgbm_model; sklearn estimator (model.joblib) via
  predict_proba(X)[0, 1].
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.ingest.lag_features import LAG_SET
from app.models.lgbm_model import apply_calibrator
from app.models.registry import CATEGORIES, get_registry
from app.predict.lag_store import get_store
from app.schemas import AllCategoriesResponse, AllPrediction, Category, Prediction


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

    def _calibrator(self, category: str) -> dict | None:
        """Stored isotonic calibrator blob (meta.json), or None when absent."""
        return self._registry.load_meta(category).get("calibrator")

    def build_vector(
        self,
        category: str,
        subject_id: str,
        features: dict[str, float] | None,
        as_of: datetime,
    ) -> list[float]:
        """Assemble the model vector for one subject.

        Priority per slot: client value > server-derived value > 0.0, where
        the server-derived value is the freshly computed lag (11 lag slots)
        or the subject's latest observed feature row (184 base slots).
        """
        feature_names = self._registry.feature_names(category)
        if not feature_names:
            raise KeyError(f"No model features registered for category '{category}'")
        features = features or {}
        store = get_store()
        lag_values = store.lags_for(category, subject_id, as_of)
        latest = store.latest_features_for(category, subject_id) or {}

        vector: list[float] = []
        for name in feature_names:
            if name in features and features[name] is not None:
                value = float(features[name])  # client overrides everything
            elif name in LAG_SET:
                value = lag_values.get(name, float("nan"))
            else:
                value = latest.get(name, 0.0)
            vector.append(value)
        return vector

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

        as_of = as_of or datetime.now(timezone.utc)
        vector = self.build_vector(category, subject_id, features, as_of)
        named = dict(zip(feature_names, vector))

        model = self._model(category)
        probability = self._probability(model, vector)
        probability = min(max(probability, 0.0), 1.0)

        state = self._registry.status(category)
        threshold = self._registry.threshold(category)
        # Calibrated score: map the raw probability through the stored isotonic
        # blob (identity when absent). The label threshold stays on the RAW
        # scale — choose_threshold was tuned on raw valid proba.
        cal_blob = self._calibrator(category)
        calibrated = apply_calibrator(cal_blob, probability)
        calibrated = min(max(float(calibrated), 0.0), 1.0)
        return Prediction(
            category=category,  # type: ignore[arg-type]
            subject_id=subject_id,
            risk_score=calibrated,
            probability=probability,
            predicted_label=probability >= threshold,
            horizon_hours=horizon_hours,
            predicted_at=datetime.now(timezone.utc),
            model_version=state.model_version,
            feature_importance=named,
        )

    def predict_all(
        self,
        subject_id: str,
        features: dict[str, float] | None,
        horizon_hours: int,
        as_of: datetime | None = None,
    ) -> AllCategoriesResponse:
        """One run over all four categories for a single incoming sensor signal.

        Same as_of for every category; per-category vector assembly and model
        calls reuse predict() verbatim, so results are identical to four
        /predict calls. Categories the channel never trained on (wrong
        subsystem — see feature_engine.CATS) come back applicable=False with
        prediction=None instead of a meaningless score.
        """
        as_of = as_of or datetime.now(timezone.utc)
        store = get_store()
        out: list[AllPrediction] = []
        for cat in CATEGORIES:
            if not store.has_subject(cat, subject_id):
                out.append(AllPrediction(category=Category(cat), applicable=False))
                continue
            p = self.predict(cat, subject_id, features, horizon_hours, as_of=as_of)
            out.append(AllPrediction(category=Category(cat), applicable=True, prediction=p))
        return AllCategoriesResponse(
            subject_id=subject_id, horizon_hours=horizon_hours, predictions=out
        )
