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

    def _probability_batch(self, model: object, X: np.ndarray) -> np.ndarray:
        """One model call over the whole N x d matrix -> (N,) array of P(class 1).

        Same dispatch as the single-path _probability, but vectorised: lgb.Booster
        via Booster.predict (native NaN handling) or a sklearn estimator via
        predict_proba(...)[..., 1]. Returns an array rather than a scalar so that
        4N single-row model invocations collapse into 4 calls per batch endpoint."""
        if is_booster(model):
            return np.asarray(model.predict(np.asarray(X, dtype=np.float64)), dtype=np.float64)
        return np.asarray(model.predict_proba(np.asarray(X, dtype=np.float64)), dtype=np.float64)[..., 1]

    def _calibrator(self, category: str) -> dict | None:
        """Stored isotonic calibrator blob (meta.json), or None when absent."""
        return self._registry.load_meta(category).get("calibrator")

    def build_vector(
        self,
        category: str,
        subject_id: str,
        features: dict[str, float | str] | None,
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
                try:
                    value = float(features[name])  # client overrides everything
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Feature '{name}' for subject '{subject_id}' must be numeric; got {features[name]!r}"
                    ) from exc
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
        features: dict[str, float | str] | None,
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

    def predict_all_batch(
        self,
        subject_ids: list[str],
        features: dict[str, dict[str, float | str]] | None,
        horizon_hours: int,
        as_of: datetime | None = None,
    ) -> list[AllCategoriesResponse]:
        """predict_all() for every channel in a batch — now vectorised.

        Model-level batching: for each of the 4 categories ONE model call over
        the full N x n_features matrix (4 calls total), instead of N single-row
        ``model.predict`` calls per category. Every model output — per-channel
        vector assembly (client > store > 0.0 / NaN lags), clipping, isotonic
        calibration and per-category decision threshold — is byte-identical to
        N consecutive ``predict_all`` calls. Only ``predicted_at`` differs: a
        batch call stamps all N x 4 predictions with a single timestamp (vs. one
        per prediction in the old loop); see test for the contract.

        Per-subject ``current_features`` overrides are supported (a channel with
        no entry falls back to the store features, ``None``). One ``as_of``
        for the whole batch; channels are returned in request order.
        """
        as_of = as_of or datetime.now(timezone.utc)
        features = features or {}
        predicted_at = datetime.now(timezone.utc)
        # per subject, accumulated in CATEGORIES order (matches predict_all)
        by_subject: dict[str, list[AllPrediction]] = {s: [] for s in subject_ids}

        for cat in CATEGORIES:
            feature_names = self._registry.feature_names(cat)
            if not feature_names:
                raise KeyError(f"No model features registered for category '{cat}'")
            # assemble one feature row per channel (same build_vector -> same output)
            rows: list[list[float]] = [
                self.build_vector(cat, subject, features.get(subject), as_of)
                for subject in subject_ids
            ]
            X = np.asarray(rows, dtype=np.float64)
            # the batch speed-up: ONE model call per category over the whole matrix
            proba = self._probability_batch(self._model(cat), X)
            proba = np.clip(proba, 0.0, 1.0)
            calibrated = np.clip(np.asarray(apply_calibrator(self._calibrator(cat), proba), dtype=np.float64), 0.0, 1.0)
            state = self._registry.status(cat)
            threshold = self._registry.threshold(cat)

            for i, subject in enumerate(subject_ids):
                named = dict(zip(feature_names, rows[i]))
                p = float(proba[i])
                c = float(calibrated[i])
                by_subject[subject].append(
                    AllPrediction(
                        category=Category(cat),
                        applicable=True,
                        prediction=Prediction(
                            category=cat,  # type: ignore[arg-type]
                            subject_id=subject,
                            risk_score=c,
                            probability=p,
                            predicted_label=bool(p >= threshold),
                            horizon_hours=horizon_hours,
                            predicted_at=predicted_at,
                            model_version=state.model_version,
                            feature_importance=named,
                        ),
                    )
                )

        return [
            AllCategoriesResponse(
                subject_id=s,
                horizon_hours=horizon_hours,
                predictions=by_subject[s],
            )
            for s in subject_ids
        ]

    def predict_all(
        self,
        subject_id: str,
        features: dict[str, float | str] | None,
        horizon_hours: int,
        as_of: datetime | None = None,
    ) -> AllCategoriesResponse:
        """One run over all four categories for a single incoming sensor signal.

        Same as_of for every category; per-category vector assembly and model
        calls reuse predict() verbatim, so results are identical to four
        /predict calls. Every category is scored — a subject without training
        history gets the documented NaN-lag vector, which LightGBM handles
        natively. (The former has_subject applicability gate is gone: journal
        subject ids come from the app domain and never match the organizer-id
        keys of the training history, so the gate fired on EVERYTHING and
        every forecast degraded to applicable=false stubs.)
        """
        as_of = as_of or datetime.now(timezone.utc)
        out: list[AllPrediction] = []
        for cat in CATEGORIES:
            p = self.predict(cat, subject_id, features, horizon_hours, as_of=as_of)
            out.append(AllPrediction(category=Category(cat), applicable=True, prediction=p))
        return AllCategoriesResponse(
            subject_id=subject_id, horizon_hours=horizon_hours, predictions=out
        )
