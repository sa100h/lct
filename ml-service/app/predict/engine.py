"""Prediction engine: turns a feature vector into a forecast.

One horizon (>= 24 h by default). Risk score is clipped to [0, 1]; the
predicted label uses a 0.5 threshold — the hackathon acceptance bar is
Precision > 0.7 / Recall > 0.5 on the organizer's test set, so the
threshold will be tuned during evaluation (app/evaluate.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.features import features_for, schema_default_vector
from app.models.registry import get_registry
from app.schemas import Prediction

# sklearn gradient-boosting classifier exposes predict_proba; typed via a
# structural alias so we avoid importing sklearn into the hot path.
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sklearn.base import BaseEstimator as AnyClassifier
else:  # pragma: no cover
    AnyClassifier = object


class PredictEngine:
    def __init__(self) -> None:
        self._registry = get_registry()
        self._models: dict[str, "AnyClassifier"] = {}

    def _model(self, category: str) -> "AnyClassifier":
        if category not in self._models:
            self._models[category] = self._registry.load(category)
        return self._models[category]

    def predict(self, category: str, subject_id: str, features: dict[str, float] | None, horizon_hours: int) -> "Prediction":
        feature_names = self._registry.feature_names(category)
        if not feature_names:
            raise KeyError(f"No model features registered for category '{category}'")

        vector = {name: float(features.get(name, 0.0)) if features else 0.0 for name in feature_names}

        model = self._model(category)
        # Note: horizon scaling is a stub. Real models will consume a
        # horizon feature directly (24 h / 72 h / ...); until then the
        # 24 h probability is returned for any requested horizon.
        probability = float(
            model.predict_proba(
                [[vector[name] for name in feature_names]],
            )[0, 1]
        )
        probability = min(max(probability, 0.0), 1.0)

        state = self._registry.status(category)
        return Prediction(
            category=category,  # type: ignore[arg-type]
            subject_id=subject_id,
            risk_score=probability,
            probability=probability,
            predicted_label=probability >= 0.5,
            horizon_hours=horizon_hours,
            predicted_at=datetime.now(timezone.utc),
            model_version=state.model_version,
            feature_importance=vector,
        )
