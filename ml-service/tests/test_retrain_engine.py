"""POST /retrain must train the production LightGBM model, not the HGB baseline.

Regression guard for a silent downgrade: the endpoint used to call
``BaselineTrainer`` unconditionally, so a scheduled retrain replaced every
LightGBM artifact (``model.lgb``) with a sklearn baseline (``model.joblib``)
and deleted the real one. The recipe itself lives in ``app.models.lgbm_train``
and its paths come from ``app.config`` (the old copy in ``scripts/train.py``
hardcoded host paths the container could not see).

Run from ml-service/:
    ./.venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import main as service
from app.models import lgbm_train
from app.models.lgbm_train import FEATURES_DIR, feature_file, train_lgbm, tuned_params
from app.schemas import RetrainRequest


# --- request schema ---------------------------------------------------------


def test_engine_defaults_to_lgbm():
    assert RetrainRequest().engine == "lgbm"


def test_engine_accepts_hgb():
    assert RetrainRequest(engine="hgb").engine == "hgb"


def test_engine_rejects_unknown_value():
    with pytest.raises(ValidationError):
        RetrainRequest(engine="xgboost")


# --- feature-file resolution (config-driven, no host paths) -----------------


def test_feature_file_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(lgbm_train, "FEATURES_DIR", tmp_path / "features")
    assert feature_file("sensor-failure") is None


def test_feature_file_returns_path(tmp_path, monkeypatch):
    features = tmp_path / "features"
    features.mkdir()
    (features / "features-fire-risk.parquet").write_bytes(b"")
    monkeypatch.setattr(lgbm_train, "FEATURES_DIR", features)
    assert feature_file("fire-risk") == features / "features-fire-risk.parquet"


def test_features_dir_comes_from_config():
    """The module must not carry its own hardcoded host path."""
    from app.config import FEATURES_DIR as config_features_dir

    assert FEATURES_DIR == config_features_dir


def test_train_lgbm_without_feature_file_fails_loudly(tmp_path, monkeypatch):
    """A missing parquet is an error — never a silent synthetic fallback."""
    monkeypatch.setattr(lgbm_train, "FEATURES_DIR", tmp_path / "features")
    with pytest.raises(FileNotFoundError, match="No feature file"):
        train_lgbm("sensor-failure")


# --- tuned params -----------------------------------------------------------


def test_tuned_params_none_without_file(tmp_path, monkeypatch):
    monkeypatch.setattr(lgbm_train, "TUNED_PATH", tmp_path / "lgbm-tuned-results.json")
    assert tuned_params("sensor-failure") is None


def test_tuned_params_reads_category_entry(tmp_path, monkeypatch):
    path = tmp_path / "lgbm-tuned-results.json"
    path.write_text(
        '{"per_category": {"fire-risk": {"params": {"num_leaves": 31}, "best_iteration": 120}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(lgbm_train, "TUNED_PATH", path)
    assert tuned_params("fire-risk") == {"params": {"num_leaves": 31}, "rounds": 120}
    assert tuned_params("sensor-failure") is None


# --- endpoint dispatch ------------------------------------------------------


@pytest.fixture
def spies(monkeypatch):
    """Replace trainers, registry and LagStore with recording spies."""
    calls = {"lgbm": [], "hgb": [], "refreshed": []}

    def fake_train_lgbm(category, **kwargs):
        calls["lgbm"].append(category)
        return {"auc": 0.93}

    class FakeBaseline:
        def fit(self, category, **kwargs):
            calls["hgb"].append(category)
            return {"test_auc": 0.51}

    monkeypatch.setattr(service, "train_lgbm", fake_train_lgbm)
    monkeypatch.setattr(service, "BaselineTrainer", FakeBaseline)
    monkeypatch.setattr(
        service,
        "get_registry",
        lambda: SimpleNamespace(status=lambda cat: SimpleNamespace(state="trained")),
    )
    monkeypatch.setattr(
        service, "get_store", lambda: SimpleNamespace(refresh=calls["refreshed"].append)
    )
    return calls


@pytest.fixture
def client(spies):
    from fastapi.testclient import TestClient

    return TestClient(service.app)


def test_retrain_defaults_to_lgbm(client, spies):
    response = client.post("/retrain", json={"category": "fire-risk"})
    assert response.status_code == 200
    body = response.json()
    assert spies["lgbm"] == ["fire-risk"]
    assert spies["hgb"] == []
    assert body["engines"] == {"fire-risk": "lgbm"}
    assert body["retrained"] == {"fire-risk": "trained"}
    # Serve-time lags are refreshed after every category.
    assert spies["refreshed"] == ["fire-risk"]


def test_retrain_hgb_is_opt_in(client, spies):
    response = client.post("/retrain", json={"category": "fire-risk", "engine": "hgb"})
    assert response.status_code == 200
    assert spies["hgb"] == ["fire-risk"]
    assert spies["lgbm"] == []
    assert response.json()["engines"] == {"fire-risk": "hgb"}


def test_retrain_without_category_covers_all_four(client, spies):
    body = client.post("/retrain", json={}).json()
    assert spies["lgbm"] == [c.value for c in service.Category]
    assert len(body["engines"]) == 4


def test_retrain_reports_failure_per_category(monkeypatch, spies):
    """A failing category is reported, the batch keeps going, no crash."""

    def boom(category, **kwargs):
        raise FileNotFoundError("no feature file")

    monkeypatch.setattr(service, "train_lgbm", boom)
    from fastapi.testclient import TestClient

    body = TestClient(service.app).post("/retrain", json={"category": "sensor-failure"}).json()
    assert body["retrained"]["sensor-failure"] == {
        "state": "failed",
        "error": "no feature file",
    }
