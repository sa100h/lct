"""Unit tests for the ml-broker queue worker — chunked /predict_all_batch semantics.

Run from the repo root (no Docker needed — DB and client are mocked):
    ~/venvs/lct-ml/bin/python -m pytest ml-broker/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `app` package importable when pytest runs from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from datetime import datetime, timezone
from typing import cast

import httpx
import pytest

from app.config import Config
from app.db import QueueRow, _as_features
from app.forecast_flow import build_chunks
from app.queue_worker import QueueWorker

T = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def cfg() -> Config:
    return Config(
        max_attempts=3,
        retry_backoff_seconds=1.0,
        horizon_hours=24,
        forecast_batch_chunk=10,
    )


def _row(
    row_id: int = 1,
    subject: str = "ch-7",
    category: str = "fire-risk",
    journal: str = "j1",
    attempts: int = 0,
    features: dict | None = None,
) -> QueueRow:
    return QueueRow(
        id=row_id,
        category=category,
        subject_id=subject,
        as_of=T,
        priority=1,
        attempts=attempts,
        features=features if features is not None else {"sensor_temp": 71.2, "humidity": 40.0},
        forecast_journal_id=journal,
    )


def _prediction(subject: str, category: str, score: float = 0.5) -> dict:
    return {
        "category": category,
        "subject_id": subject,
        "risk_score": score,
        "predicted_label": False,
        "horizon_hours": 24,
        "model_version": "v-test",
    }


class FakeDB:
    """Records every terminal/retry state transition instead of hitting Postgres."""

    def __init__(self, rows: list[QueueRow] | None = None) -> None:
        self.rows = rows or []
        self.claims = 0
        self.claim_sizes: list[int] = []
        self.done: list[int] = []
        self.retried: list[tuple[int, int, str, float]] = []
        self.failed: list[tuple[int, int, str]] = []
        self.result_calls: list[tuple[int, dict]] = []
        self.finalized: list[str] = []

    async def claim_open_journal(self):
        return None

    async def claim_batch(self, size: int):
        self.claims += 1
        self.claim_sizes.append(size)
        out = self.rows[:size]
        if out:
            self.rows = self.rows[size:]
        return out

    async def mark_done(self, row_id: int) -> None:
        self.done.append(row_id)

    async def mark_retry(self, row_id: int, attempts: int, error: str, backoff: float) -> None:
        self.retried.append((row_id, attempts, error, backoff))

    async def mark_failed(self, row_id: int, attempts: int, error: str) -> None:
        self.failed.append((row_id, attempts, error))

    async def store_result(self, row_id: int, result: dict) -> None:
        self.result_calls.append((row_id, result))

    async def finalize_journal(self, journal_id: str) -> None:
        self.finalized.append(journal_id)

    async def close(self) -> None:
        pass


def _batch_response(rows_by_subject: dict[str, list[dict]]) -> dict:
    """BatchPredictionResponse-shaped body: one AllCategoriesResponse per subject."""
    return {
        "predictions": [
            {"subject_id": subject, "predictions": preds}
            for subject, preds in rows_by_subject.items()
        ]
    }


def _status_error(status: int, body: dict | None = None) -> httpx.HTTPStatusError:
    response = httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "http://ml/predict_all_batch"),
        json=body or {"detail": f"boom {status}"},
    )
    return httpx.HTTPStatusError(
        message=f"HTTP {status}", request=response.request, response=response
    )


def _client(*side_effects) -> httpx.AsyncClient:
    """AsyncClient whose .post returns/raises the listed effects in order.

    An effect is either an httpx.Response (success) or an Exception (to raise).
    When the list runs out, a 200 response echoing one Prediction per
    (subject, category) of the request payload is returned.
    """
    calls: list[dict] = []
    seq = list(side_effects)
    request = httpx.Request("POST", "http://ml/predict_all_batch")

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        effect = seq.pop(0) if seq else httpx.Response(
            200,
            request=request,
            json=_batch_response(
                {
                    s: [_prediction(s, c) for c in cats]
                    for s, cats in (json.get("_plan") or {}).items()
                }
            ),
        )
        if isinstance(effect, Exception):
            raise effect
        return effect

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    client._calls = calls  # type: ignore[attr-defined]
    return client


def _worker(cfg: Config, db: FakeDB, client: httpx.AsyncClient) -> QueueWorker:
    from app.db import Db

    return QueueWorker(db=cast(Db, db), client=client, cfg=cfg, wake=asyncio.Event())


def test_batch_payload_and_spread(cfg):
    """One POST per chunk: per-channel features, one as_of, results spread back."""
    rows = [
        _row(1, "ch-1", "fire-risk"),
        _row(2, "ch-1", "sensor-failure"),
        _row(3, "ch-2", "fire-risk"),
    ]
    plan = {"ch-1": ["fire-risk", "sensor-failure"], "ch-2": ["fire-risk"]}
    db = FakeDB(rows=rows)
    calls: list[dict] = []

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        body = _batch_response(
            {s: [_prediction(s, c) for c in plan[s]] for s in (json or {}).get("subject_ids", [])}
        )
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    worker = _worker(cfg, db, client)

    handled = asyncio.run(worker._drain_once())

    assert handled == 3
    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith("/predict_all_batch")
    assert call["json"]["subject_ids"] == ["ch-1", "ch-2"]
    assert call["json"]["current_features"]["ch-1"] == {"sensor_temp": 71.2, "humidity": 40.0}
    assert call["json"]["as_of"] == T.isoformat()
    assert call["json"]["horizon_hours"] == 24
    assert sorted(db.done) == [1, 2, 3]
    assert {r[0] for r in db.result_calls} == {1, 2, 3}
    scored = {r[0]: r[1] for r in db.result_calls if "risk_score" in r[1]}
    assert sorted(scored) == [1, 2, 3]  # все 3 строки получили Prediction
    assert all(r["risk_score"] == 0.5 for r in scored.values())
    assert worker.stats["batch_calls"] == 1 and worker.stats["done"] == 3


def test_non_applicable_marks_done_with_stub_result(cfg):
    """applicable=false -> done with the stub result (forecast_description later
    shows status_code=unpredictable; no /predict fallback)."""
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk")])
    body = _batch_response({"ch-1": [{"category": "fire-risk", "applicable": False}]})
    client = _client(httpx.Response(200, request=httpx.Request("POST", "http://ml/predict_all_batch"), json=body))
    worker = _worker(cfg, db, client)

    asyncio.run(worker._drain_once())

    assert db.done == [1]
    assert db.result_calls == [(1, {"applicable": False, "category": "fire-risk", "subject_id": "ch-1"})]
    assert db.finalized == ["j1"]


def test_unknown_subject_category_skipped(cfg):
    """A response entry outside the chunk's (subject, category) set is ignored."""
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk")])
    body = _batch_response(
        {
            "ch-999": [{"category": "fire-risk", "applicable": False}],  # not our chunk
            "ch-1": [{"category": "wear-unknown", "applicable": False}],  # not our chunk
        }
    )
    client = _client(httpx.Response(200, request=httpx.Request("POST", "http://ml/predict_all_batch"), json=body))
    worker = _worker(cfg, db, client)

    handled = asyncio.run(worker._drain_once())

    assert handled == 0
    assert db.done == [] and db.result_calls == [] and db.failed == []
    assert worker.stats["batch_calls"] == 1


def test_5xx_chunk_retried_then_failed(cfg):
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk"), _row(2, "ch-2", "fire-risk")])
    worker = _worker(cfg, db, _client(_status_error(503, {"detail": "overloaded"})))

    asyncio.run(worker._drain_once())

    assert sorted(db.retried) == [
        (1, 1, "HTTP 503: {\"detail\":\"overloaded\"}", 1.0),
        (2, 1, "HTTP 503: {\"detail\":\"overloaded\"}", 1.0),
    ]
    assert db.done == [] and db.failed == []
    assert worker.stats["retried"] == 2

    # attempts exhausted -> whole chunk failed
    db2 = FakeDB(
        rows=[_row(1, "ch-1", "fire-risk", attempts=2), _row(2, "ch-2", "fire-risk", attempts=2)]
    )
    worker2 = _worker(cfg, db2, _client(_status_error(503, {"detail": "overloaded"})))
    asyncio.run(worker2._drain_once())
    assert sorted(db2.failed) == [
        (1, 3, "HTTP 503: {\"detail\":\"overloaded\"}"),
        (2, 3, "HTTP 503: {\"detail\":\"overloaded\"}"),
    ]
    assert db2.retried == [] and db2.done == []


def test_4xx_chunk_failed_no_retry(cfg):
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk")])
    worker = _worker(cfg, db, _client(_status_error(422, {"detail": "bad payload"})))

    asyncio.run(worker._drain_once())

    assert db.failed == [(1, 1, "HTTP 422: {\"detail\":\"bad payload\"}")]
    assert db.retried == [] and db.done == []
    assert db.finalized == ["j1"]


def test_transport_error_chunk_retried(cfg):
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk"), _row(2, "ch-2", "fire-risk")])
    worker = _worker(cfg, db, _client(httpx.ConnectError("connection refused")))

    asyncio.run(worker._drain_once())

    assert [r[0] for r in db.retried] == [1, 2]
    assert all("ConnectError" in r[2] for r in db.retried)
    assert db.done == [] and db.failed == []


def test_read_timeout_splits_chunk_until_it_fits(cfg):
    """An oversized chunk that times out is halved and retried, not penalised.

    The ml-service here answers only small payloads (<= 20 subjects); the
    60-subject chunk times out until the split brings it under that. No row
    may burn an attempt and everything must end up done.
    """
    cats = ("sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear")
    n_subjects = 60
    rows = [
        _row(s * len(cats) + c + 1, f"ch-{s}", cat)
        for s in range(n_subjects)
        for c, cat in enumerate(cats)
    ]
    cfg = Config(
        max_attempts=3,
        retry_backoff_seconds=1.0,
        horizon_hours=24,
        forecast_batch_chunk=n_subjects,
        predict_timeout_seconds=1.0,
    )
    db = FakeDB(rows=rows)
    sizes: list[int] = []

    async def fake_post(url, json=None, timeout=None):
        subjects = list((json or {}).get("subject_ids", []))
        sizes.append(len(subjects))
        assert timeout == 1.0, "batch call must use predict_timeout_seconds"
        if len(subjects) > 20:
            raise httpx.ReadTimeout("read timed out")
        body = _batch_response({s: [_prediction(s, c) for c in cats] for s in subjects})
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    worker = _worker(cfg, db, client)

    handled = asyncio.run(worker._process_chunk(build_chunks(rows, n_subjects)[0]))

    assert handled == len(rows)
    assert len(db.done) == len(rows)
    assert db.retried == [] and db.failed == []
    assert sizes[0] == n_subjects          # oversized first attempt
    assert max(sizes) == n_subjects        # never grows
    assert min(sizes) <= 20                # eventually fits the service
    assert sizes.count(n_subjects) == 1    # split only once per level


def test_timeout_at_floor_size_uses_normal_retry(cfg):
    """Below MIN_SPLIT_SUBJECTS a timeout is a real service problem -> retry."""
    db = FakeDB(rows=[_row(1, "ch-1", "fire-risk"), _row(2, "ch-2", "fire-risk")])
    worker = _worker(cfg, db, _client(httpx.ReadTimeout("read timed out")))

    asyncio.run(worker._drain_once())

    assert [r[0] for r in db.retried] == [1, 2]
    assert all("ReadTimeout" in r[2] for r in db.retried)
    assert db.done == [] and db.failed == []


def test_drain_once_three_subjects_chunk_one(cfg):
    """chunk=1 -> one POST per subject; all rows done; batch_calls counts POSTs."""
    cfg = Config(max_attempts=3, retry_backoff_seconds=1.0, horizon_hours=24, forecast_batch_chunk=1)
    plan = {"ch-1": ["fire-risk", "sensor-failure"], "ch-2": ["fire-risk"], "ch-3": ["fire-risk"]}
    rows = [
        _row(1, "ch-1", "fire-risk"),
        _row(2, "ch-1", "sensor-failure"),
        _row(3, "ch-2", "fire-risk"),
        _row(4, "ch-3", "fire-risk"),
    ]
    db = FakeDB(rows=rows)
    calls: list[dict] = []

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        body = _batch_response(
            {s: [_prediction(s, c) for c in plan[s]]
             for s in (json or {}).get("subject_ids", [])}
        )
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    worker = _worker(cfg, db, client)

    handled = asyncio.run(worker._drain_once())

    assert handled == 4
    assert [c["json"]["subject_ids"] for c in calls] == [["ch-1"], ["ch-2"], ["ch-3"]]
    assert len(db.done) == 4
    assert worker.stats["batch_calls"] == 3


def test_idle_flag_turns_off_waiting(cfg):
    """After a productive tick _run must not sleep POLL_SECONDS.

    The default responder echoes every (subject, category) of the payload, so
    the drain handles the row and _idle flips False."""
    rows = [_row(1, "ch-1", "fire-risk")]
    plan = {"ch-1": ["fire-risk"]}
    db = FakeDB(rows=rows)
    calls: list[dict] = []

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        body = _batch_response(
            {s: [_prediction(s, c) for c in plan[s]]
             for s in (json or {}).get("subject_ids", [])}
        )
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    worker = _worker(cfg, db, client)
    assert worker._idle is True

    asyncio.run(worker._drain_once())

    assert calls, "POST /predict_all_batch must have been made"
    assert worker._idle is False  # next _run tick must NOT sleep POLL_SECONDS


def test_claim_rows_scales_with_categories(cfg):
    db = FakeDB()
    worker = _worker(cfg, db, _client())
    assert worker._claim_rows() == 40  # 10 subjects * 4 categories
    asyncio.run(worker._drain_once())  # empty queue is a no-op
    assert db.claim_sizes == [40]


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"a": 1.0, "b": None, "c": "3", "d": "bad"}, {"a": 1.0, "c": "3", "d": "bad"}),
        ({}, {}),
        (None, {}),
        ('{"x": 2}', {"x": 2.0}),
        ("not json", {}),
        ([1, 2], {}),
    ],
)
def test_as_features_normalization(value, expected):
    assert _as_features(value) == expected
