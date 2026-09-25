"""Unit tests: POST /predict_all — all 4 categories in one run.

Fakes mirror tests/test_engine_vector.py: the engine's registry and LagStore
are replaced, so the tests pin the predict_all CONTRACT (category order,
applicability gate, client override, endpoint wiring), not the artifacts.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from app.ingest.lag_features import LAG_FEATURES
from app.predict import engine as engine_mod
from app.predict.engine import PredictEngine


class FakeModel:
    """Sklearn-shaped stub: P(class 1) = clamp(0.1 * x0), x0 = first feature.

    Client overrides and store values push x0, so they change the probability
    measurably — the contract tests assert exactly that coupling.
    """

    def predict_proba(self, X):
        X = np.asarray(X, dtype=np.float64)
        p = np.clip(0.1 * X[:, 0], 0.0, 1.0)
        return np.column_stack([1.0 - p, p])


class FakeRegistryAll:
    """Same 2 base + 1 lag feature names for every category."""

    def __init__(self, names: list[str]) -> None:
        self._names = names

    def feature_names(self, category: str) -> list[str]:
        return self._names

    def status(self, category: str):
        from dataclasses import dataclass

        @dataclass
        class S:
            model_version: str = "v-test"

        return S()

    def threshold(self, category: str) -> float:
        return 0.5

    def load_meta(self, category: str) -> dict:
        return {}

    def load(self, category: str):
        return FakeModel()


class FakeStoreAll:
    """lags/latest/has_subject: subject s1 trained sensor-failure + fire-risk,
    NOT unauthorized-access / infrastructure-wear. s0 has no history at all."""

    def lags_for(self, category: str, subject_id: str, as_of):
        if subject_id == "s0":
            return {k: float("nan") for k in LAG_FEATURES}
        return {k: (3.0 if k == LAG_FEATURES[0] else float("nan")) for k in LAG_FEATURES}

    def latest_features_for(self, category: str, subject_id: str):
        if subject_id == "s0":
            return None
        return {"f_a": 1.0, "f_b": 2.0}

    def has_subject(self, category: str, subject_id: str) -> bool:
        if subject_id == "s0":
            return category == "sensor-failure"  # only one category knows it
        return category in ("sensor-failure", "fire-risk")


@pytest.fixture
def eng(monkeypatch):
    names = ["f_a", "f_b", LAG_FEATURES[0]]
    store = FakeStoreAll()
    monkeypatch.setattr(engine_mod, "get_store", lambda: store)
    e = PredictEngine()
    e._registry = FakeRegistryAll(names)  # type: ignore[assignment]
    return e, names, store


def test_predict_all_returns_all_categories(eng):
    e, _, _ = eng
    resp = e.predict_all("s1", {}, 24)
    assert [p.category.value for p in resp.predictions] == [
        "sensor-failure",
        "fire-risk",
        "unauthorized-access",
        "infrastructure-wear",
    ]
    assert resp.subject_id == "s1"
    assert resp.horizon_hours == 24


def test_predict_all_applicability_gate(eng):
    e, _, _ = eng
    resp = e.predict_all("s1", {}, 24)
    by_cat = {p.category.value: p for p in resp.predictions}
    assert by_cat["sensor-failure"].applicable and by_cat["sensor-failure"].prediction is not None
    assert by_cat["fire-risk"].applicable and by_cat["fire-risk"].prediction is not None
    assert by_cat["unauthorized-access"].applicable is False
    assert by_cat["unauthorized-access"].prediction is None
    assert by_cat["infrastructure-wear"].applicable is False
    assert by_cat["infrastructure-wear"].prediction is None


def test_predict_all_predictions_carry_scores(eng):
    e, _, _ = eng
    resp = e.predict_all("s1", {}, 24)
    by_cat = {p.category.value: p for p in resp.predictions}
    # s1: f_a=1.0 from store -> p = clamp(0.1*1.0) = 0.1
    assert abs(by_cat["sensor-failure"].prediction.probability - 0.1) < 1e-6
    assert 0.0 <= by_cat["sensor-failure"].prediction.risk_score <= 1.0
    assert by_cat["sensor-failure"].prediction.predicted_label is False
    assert by_cat["sensor-failure"].prediction.model_version == "v-test"


def test_predict_all_client_override(eng):
    e, _, _ = eng
    base = e.predict_all("s1", {}, 24)
    with_client = e.predict_all("s1", {"f_a": 9.0}, 24)
    p_store = base.predictions[0].prediction.probability
    p_client = with_client.predictions[0].prediction.probability
    assert p_store == pytest.approx(0.1)
    assert p_client == pytest.approx(0.9), "client base feature must win over store"


def test_predict_all_no_history_subject_still_scores_applicable(eng):
    e, _, _ = eng
    resp = e.predict_all("s0", {}, 24)
    by_cat = {p.category.value: p for p in resp.predictions}
    # s0 is applicable only to sensor-failure; NaN lags -> base f_a missing -> 0.0 -> p=0
    assert by_cat["sensor-failure"].applicable
    assert by_cat["sensor-failure"].prediction.probability == pytest.approx(0.0)
    assert by_cat["fire-risk"].applicable is False


# --------------------------------------------------------------------------- #
# endpoint wiring
# --------------------------------------------------------------------------- #


def test_predict_all_endpoint(eng, monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    e, _, _ = eng
    app.state.engine = e
    client = TestClient(app)
    r = client.post("/predict_all", json={"subject_id": "s1", "current_features": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject_id"] == "s1"
    assert len(body["predictions"]) == 4
    cats = [p["category"] for p in body["predictions"]]
    assert cats == [
        "sensor-failure",
        "fire-risk",
        "unauthorized-access",
        "infrastructure-wear",
    ]
    ua = body["predictions"][2]
    assert ua["applicable"] is False and ua["prediction"] is None
