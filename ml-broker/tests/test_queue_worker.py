"""Unit tests for the ml-broker queue worker (retry / 5xx / 4xx / max-attempts).

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
from app.queue_worker import QueueWorker


@pytest.fixture()
def cfg() -> Config:
    return Config(max_attempts=3, retry_backoff_seconds=1.0, horizon_hours=24)


def _row(row_id: int = 1, attempts: int = 0, features: dict | None = None) -> QueueRow:
    return QueueRow(
        id=row_id,
        category="fire-risk",
        subject_id="ch-7",
        as_of=datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc),
        priority=0,
        attempts=attempts,
        features=features if features is not None else {"sensor_temp": 71.2, "humidity": 40.0},
    )


class FakeDB:
    """Records every terminal/retry state transition instead of hitting Postgres."""

    def __init__(self, rows: list[QueueRow] | None = None) -> None:
        self.rows = rows or []
        self.claims = 0
        self.done: list[int] = []
        self.retried: list[tuple[int, int, str, float]] = []
        self.failed: list[tuple[int, int, str]] = []
        self.result_calls: list[tuple[int, dict]] = []

    async def claim_batch(self, size: int):
        self.claims += 1
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

    async def close(self) -> None:
        pass


def _status_error(status: int, body: dict | None = None) -> httpx.HTTPStatusError:
    response = httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "http://ml/predict"),
        json=body or {"detail": f"boom {status}"},
    )
    return httpx.HTTPStatusError(
        message=f"HTTP {status}", request=response.request, response=response
    )


def _client(*side_effects) -> httpx.AsyncClient:
    """AsyncClient whose .post returns/raises the listed effects in order.

    An effect is either an httpx.Response (success) or an Exception (to raise).
    When the list runs out, a 200 success response is returned.
    """
    calls: list[dict] = []
    seq = list(side_effects)
    request = httpx.Request("POST", "http://ml/predict")

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        effect = seq.pop(0) if seq else httpx.Response(200, request=request, json=_ok_body())
        if isinstance(effect, Exception):
            raise effect
        return effect

    def _ok_body():
        return {
            "category": "fire-risk",
            "risk_score": 0.5,
            "predicted_label": False,
            "horizon_hours": 24,
            "model_version": "v-test",
        }

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    client._calls = calls  # type: ignore[attr-defined]
    return client


def _worker(cfg: Config, db: FakeDB, client: httpx.AsyncClient) -> QueueWorker:
    from app.db import Db

    return QueueWorker(db=cast(Db, db), client=client, cfg=cfg, wake=asyncio.Event())


def test_success_marks_done_and_persists_prediction(cfg):
    db = FakeDB()
    client = _client()
    worker = _worker(cfg, db, client)

    asyncio.run(worker._process_row(_row()))

    assert db.done == [1]
    assert db.retried == [] and db.failed == []
    assert db.result_calls[0][0] == 1
    assert db.result_calls[0][1]["risk_score"] == 0.5
    assert client._calls[0]["json"]["horizon_hours"] == 24
    assert client._calls[0]["json"]["current_features"] == {"sensor_temp": 71.2, "humidity": 40.0}


def test_5xx_is_retried_with_backoff_not_raised(cfg):
    """Regression: a bare `raise` on 5xx stranded the row `running` forever
    (claim_batch only takes `pending`). Now it must hit mark_retry."""
    db = FakeDB()
    client = _client(_status_error(503, {"detail": "overloaded"}))
    worker = _worker(cfg, db, client)

    # must NOT raise
    asyncio.run(worker._process_row(_row()))

    assert db.retried == [(1, 1, "HTTP 503: {\"detail\":\"overloaded\"}", 1.0)]
    assert db.done == [] and db.failed == []
    assert worker.stats["retried"] == 1


def test_4xx_is_failed_immediately_no_retry(cfg):
    db = FakeDB()
    client = _client(_status_error(422, {"detail": "bad payload"}))
    worker = _worker(cfg, db, client)

    asyncio.run(worker._process_row(_row(attempts=2)))  # even at the last attempt: no retry

    assert db.failed == [(1, 3, "HTTP 422: {\"detail\":\"bad payload\"}")]
    assert db.retried == [] and db.done == []
    assert worker.stats["failed"] == 1


def test_attempts_exhausted_goes_to_failed(cfg):
    db = FakeDB()
    client = _client(_status_error(500), _status_error(500), _status_error(500))
    worker = _worker(cfg, db, client)

    asyncio.run(worker._process_row(_row(attempts=0)))  # attempt 1 -> retry
    asyncio.run(worker._process_row(_row(attempts=1)))  # attempt 2 -> retry
    asyncio.run(worker._process_row(_row(attempts=2)))  # attempt 3 == max -> failed

    assert len(db.retried) == 2
    assert db.failed == [(1, 3, "HTTP 500: {\"detail\":\"boom 500\"}")]
    assert worker.stats["failed"] == 1


def test_transport_error_is_retried(cfg):
    db = FakeDB()
    client = _client(httpx.ConnectError("connection refused"))
    worker = _worker(cfg, db, client)

    asyncio.run(worker._process_row(_row()))

    assert db.retried and db.retried[0][0] == 1
    assert "ConnectError" in db.retried[0][2]


def test_drain_once_bounds_batch_and_stats(cfg):
    cfg = Config(max_attempts=3, retry_backoff_seconds=1.0, horizon_hours=24, queue_batch=2)
    db = FakeDB(rows=[_row(i) for i in (1, 2, 3)])
    client = _client()
    worker = _worker(cfg, db, client)

    handled = asyncio.run(worker._drain_once())
    assert handled == 2  # batch size 2, row 3 stays pending
    assert db.done == [1, 2]
    assert db.rows == [db.rows[0]] and db.rows[0].id == 3
    assert worker.stats["done"] == 2


def test_drain_once_empty_queue_is_noop(cfg):
    db = FakeDB()
    worker = _worker(cfg, db, _client())

    handled = asyncio.run(worker._drain_once())
    assert handled == 0
    assert db.claims == 1


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
