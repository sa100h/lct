"""ml-service smoke tests (run: pytest -q)."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app, Category
from app.models.baseline import BaselineTrainer
from app.models.features import features_for, schema_default_vector


def _ensure_models():
    """Train all categories once (cached in registry) so endpoints are usable."""
    from app.models.registry import get_registry

    trainer = BaselineTrainer()
    registry = get_registry()
    for cat in Category:
        if registry.status(cat.value).state != "trained":
            trainer.fit(cat.value)


def _client():
    """TestClient as a context manager so the app lifespan (engine setup) runs."""
    return TestClient(app)


def test_status_returns_ready():
    _ensure_models()
    with _client() as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "ready"
        assert set(body["models"]) == {c.value for c in Category}


def test_predict_all_categories():
    _ensure_models()
    with _client() as client:
        for cat in Category:
            features = schema_default_vector(cat.value)
            resp = client.post(
                "/predict",
                json={
                    "category": cat.value,
                    "subject_id": "test-subject",
                    "current_features": features,
                    "horizon_hours": 24,
                },
            )
            assert resp.status_code == 200, f"{cat.value}: {resp.text}"
            body = resp.json()
            assert 0.0 <= body["risk_score"] <= 1.0
            assert body["horizon_hours"] == 24
            assert body["model_version"] != "none"


def test_predict_unknown_category_rejected():
    _ensure_models()
    with _client() as client:
        resp = client.post(
            "/predict",
            json={"category": "bogus", "subject_id": "x", "current_features": {}},
        )
        assert resp.status_code == 422


def test_features_schema_consistency():
    for cat in Category:
        names = features_for(cat.value)
        assert len(names) == 6
        assert len(set(names)) == 6


@pytest.mark.requires_real_data
def test_models_have_lag_features_and_load():
    """T7: real-data models carry the 11 lag feature names and their artifact loads.

    Requires the locally-trained production models (195-feature real data)
    in ``ml-service/models/`` — production box only; skipped in CI (see
    conftest).

    Baseline (synthetic 6-feature) categories are a different artifact:
    they must match the baseline schema and still load. Asserting 195+
    features for every category is wrong — only real-data models (>= 195
    features) are expected to carry the lag feature names.
    """
    from app.ingest.lag_features import LAG_FEATURES
    from app.models.registry import get_registry

    _ensure_models()
    registry = get_registry()
    for cat in Category:
        names = registry.feature_names(cat.value)
        model = registry.load(cat.value)
        assert model is not None
        assert hasattr(model, "predict") or hasattr(model, "predict_proba")
        if len(names) >= 195:
            # real-data model: full feature vector + lag names
            missing = [k for k in LAG_FEATURES if k not in names]
            assert not missing, f"{cat.value}: lag names missing from feature list: {missing}"
        else:
            # synthetic baseline: exactly this category's 6 baseline features
            # (each category has its own 6-signal schema)
            assert set(names) == set(features_for(cat.value)), (
                f"{cat.value}: baseline schema mismatch: {sorted(names)}"
            )

