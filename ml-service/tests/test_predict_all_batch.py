"""Unit tests: POST /predict_all_batch — per-channel overrides + one as_of.

Reuses the fakes from test_predict_all.py: the contract under test is
  * per-subject ``current_features`` (``{subject_id: {feature: value}}``) —
    a channel without an entry falls back to store features (None);
  * ``as_of`` is forwarded to the engine (one timestamp for the whole batch);
  * the endpoint returns one AllCategoriesResponse per requested channel,
    in request order, with applicable=False gates intact.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.main import app
from app.schemas import BatchPredictionRequest
from tests.test_predict_all import FakeRegistryAll, FakeStoreAll  # shared fakes
from fastapi.testclient import TestClient


def test_batch_request_per_channel_and_as_of_are_optional():
    req = BatchPredictionRequest(
        subject_ids=["s1", "s2"],
        current_features={"s1": {"f_a": 9.0}},
    )
    assert req.as_of is None
    assert req.horizon_hours == 24  # PREDICTION_HORIZON_HOURS default
    assert req.current_features == {"s1": {"f_a": 9.0}}


def test_batch_requires_non_empty_subjects():
    from pydantic import ValidationError

    try:
        BatchPredictionRequest(subject_ids=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("empty subject_ids must be rejected")


def test_endpoint_batch_orders_and_applies_per_channel_override(
    monkeypatch,
):
    from app.predict import engine as engine_mod

    store = FakeStoreAll()
    monkeypatch.setattr(engine_mod, "get_store", lambda: store)
    from app.predict.engine import PredictEngine

    e = PredictEngine()
    from app.ingest.lag_features import LAG_FEATURES

    e._registry = FakeRegistryAll(["f_a", "f_b", LAG_FEATURES[0]])  # type: ignore[assignment]
    app.state.engine = e

    client = TestClient(app)
    r = client.post(
        "/predict_all_batch",
        json={
            "subject_ids": ["s1", "s2"],
            "current_features": {"s2": {"f_a": 9.0}},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["horizon_hours"] == 24
    preds = body["predictions"]
    assert [p["subject_id"] for p in preds] == ["s1", "s2"], "request order preserved"

    def sf_score(resp: dict) -> float:
        by_cat = {p["category"]: p for p in resp["predictions"]}
        return by_cat["sensor-failure"]["prediction"]["probability"]

    # s1: no override -> store f_a=1.0 -> p=0.1 ; s2: override f_a=9.0 -> p=0.9
    assert sf_score(preds[0]) == 0.1
    assert sf_score(preds[1]) == 0.9


def test_endpoint_batch_as_of_forwarded(monkeypatch):
    """The as_of from the request must reach the engine (not be dropped)."""
    captured: dict = {}

    from app.predict import engine as engine_mod
    from app.predict.engine import PredictEngine

    orig_batch = PredictEngine.predict_all_batch

    def spy_batch(self, subject_ids, features, horizon_hours, as_of=None):
        captured["as_of"] = as_of
        captured["features"] = features
        return orig_batch(self, subject_ids, features, horizon_hours, as_of=as_of)

    PredictEngine.predict_all_batch = spy_batch  # type: ignore[method-assign]
    try:
        store = FakeStoreAll()
        monkeypatch.setattr(engine_mod, "get_store", lambda: store)
        e = PredictEngine()
        from app.ingest.lag_features import LAG_FEATURES

        e._registry = FakeRegistryAll(["f_a", "f_b", LAG_FEATURES[0]])  # type: ignore[assignment]
        app.state.engine = e

        ts = "2026-09-26T10:00:00Z"
        client = TestClient(app)
        r = client.post(
            "/predict_all_batch",
            json={"subject_ids": ["s1"], "as_of": ts},
        )
        assert r.status_code == 200, r.text
        assert captured["as_of"] == datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
        assert captured["features"] == {}
    finally:
        PredictEngine.predict_all_batch = orig_batch  # type: ignore[method-assign]


# --------------------------------------------------------------------------- #
# coverage gate in the batch path
# --------------------------------------------------------------------------- #


def test_batch_applies_coverage_gate_per_category(monkeypatch):
    """Uncovered (category, channel) pairs come back applicable=False/None.

    The batch path must gate exactly like ``predict_all`` — otherwise the
    forecast journal would store a constant for channels the category never
    trained on."""
    from app.predict import engine as engine_mod
    from app.predict.engine import PredictEngine
    from app.ingest.lag_features import LAG_FEATURES

    store = FakeStoreAll()
    monkeypatch.setattr(engine_mod, "get_store", lambda: store)
    e = PredictEngine()
    e._registry = FakeRegistryAll(["f_a", "f_b", LAG_FEATURES[0]])  # type: ignore[assignment]
    app.state.engine = e

    client = TestClient(app)
    r = client.post("/predict_all_batch", json={"subject_ids": ["s1", "s0"]})
    assert r.status_code == 200, r.text
    preds = r.json()["predictions"]
    assert [p["subject_id"] for p in preds] == ["s1", "s0"]

    s1 = {p["category"]: p for p in preds[0]["predictions"]}
    assert s1["sensor-failure"]["applicable"] is True
    assert s1["fire-risk"]["applicable"] is True
    for cat in ("unauthorized-access", "infrastructure-wear"):
        assert s1[cat]["applicable"] is False
        assert s1[cat]["prediction"] is None

    # s0 trained sensor-failure only
    s0 = {p["category"]: p for p in preds[1]["predictions"]}
    assert s0["sensor-failure"]["applicable"] is True
    for cat in ("fire-risk", "unauthorized-access", "infrastructure-wear"):
        assert s0[cat]["applicable"] is False
        assert s0[cat]["prediction"] is None


def test_batch_matches_predict_all_including_applicability(monkeypatch):
    """Batch entries must equal the single-subject predict_all result
    (same applicability, same probability) — the batch is only a speed-up."""
    from app.predict import engine as engine_mod
    from app.predict.engine import PredictEngine
    from app.ingest.lag_features import LAG_FEATURES

    store = FakeStoreAll()
    monkeypatch.setattr(engine_mod, "get_store", lambda: store)
    e = PredictEngine()
    e._registry = FakeRegistryAll(["f_a", "f_b", LAG_FEATURES[0]])  # type: ignore[assignment]

    batch = e.predict_all_batch(["s1", "s0"], {}, 24)
    for entry in batch:
        single = e.predict_all(entry.subject_id, {}, 24)
        for a, b in zip(entry.predictions, single.predictions):
            assert a.category == b.category
            assert a.applicable is b.applicable
            if b.prediction is None:
                assert a.prediction is None
            else:
                assert a.prediction is not None
                assert a.prediction.probability == b.prediction.probability
