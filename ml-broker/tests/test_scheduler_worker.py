"""Unit tests for the ml_schedule scheduler worker.

DB and HTTP are mocked — no Docker, no Postgres, no network. Run from the repo
root:

    ~/venvs/lct-ml/bin/python -m pytest ml-broker/tests -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

import httpx
import pytest

from app.config import Config
from app.db import Db, ScheduleJob
from app.scheduler_worker import SchedulerWorker, _all_failed

UTC = timezone.utc
NOW = datetime.now(UTC)


@pytest.fixture()
def cfg() -> Config:
    return Config(retrain_timeout_seconds=5.0, scheduler_missed_grace_seconds=60.0)


class FakeDB:
    """Mimics `claim_due_jobs`' contract: run `plan` once per due row.

    The real method claims within one transaction with FOR UPDATE SKIP LOCKED;
    what the worker depends on is only that every due row is passed to `plan`
    exactly once and that the rows it says "fire" come back as ScheduleJobs.
    """

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.planned: list[tuple[str, bool]] = []
        self.next_runs: dict[str, datetime] = {}
        self.started: list[tuple[str | None, str]] = []
        self.finished: list[tuple[str, str, dict]] = []
        self._seq = 0

    async def claim_due_jobs(self, plan):
        jobs: list[ScheduleJob] = []
        for row in self.rows:
            next_run, fire = plan(dict(row))
            self.planned.append((row["name"], fire))
            self.next_runs[row["name"]] = next_run
            if fire:
                jobs.append(
                    ScheduleJob(
                        id=row["id"],
                        kind=row["kind"],
                        name=row["name"],
                        cron_expr=row["cron_expr"],
                        args=row.get("args") or {},
                        next_run_at=next_run,
                    )
                )
        return jobs

    async def start_retrain_run(self, category: str | None) -> str:
        self._seq += 1
        run_id = f"run-{self._seq}"
        self.started.append((category, run_id))
        return run_id

    async def finish_retrain_run(self, run_id: str, status: str, metrics: dict) -> None:
        self.finished.append((run_id, status, metrics))

    async def close(self) -> None:
        pass


def _row(
    name: str = "daily-retrain",
    kind: str = "retrain",
    cron: str = "30 4 * * *",
    args: dict | None = None,
    due_seconds_ago: int | None = 0,
    next_run_at: datetime | None = None,
) -> dict:
    """A ml_schedule row; due_seconds_ago=None means 'never scheduled' (NULL)."""
    if next_run_at is None and due_seconds_ago is not None:
        next_run_at = NOW - timedelta(seconds=due_seconds_ago)
    return {
        "id": f"id-{name}",
        "kind": kind,
        "name": name,
        "cron_expr": cron,
        "args": args or {},
        "last_run_at": None,
        "next_run_at": next_run_at,
    }


def _response(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, request=httpx.Request("POST", "http://ml/retrain"), json=body
    )


def _client(*effects) -> httpx.AsyncClient:
    """AsyncClient whose .post returns/raises the given effects in order."""
    calls: list[dict] = []
    seq = list(effects)

    async def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        effect = seq.pop(0) if seq else _response({"retrained": {"sensor-failure": "trained"}})
        if isinstance(effect, Exception):
            raise effect
        return effect

    client = httpx.AsyncClient()
    client.post = fake_post  # type: ignore[assignment]
    client._calls = calls  # type: ignore[attr-defined]
    return client


def _worker(cfg: Config, db: FakeDB, client: httpx.AsyncClient) -> SchedulerWorker:
    return SchedulerWorker(db=cast(Db, db), client=client, cfg=cfg)


def _calls(client: httpx.AsyncClient) -> list[dict]:
    return client._calls  # type: ignore[attr-defined]


async def _await_retrain(worker: SchedulerWorker) -> None:
    """Let the background retrain task finish (the worker does not await it)."""
    task = worker._retrain_task
    assert task is not None, "a retrain task must have been started"
    await task


# ---- dispatch --------------------------------------------------------------


def test_due_retrain_runs_and_records_a_done_run(cfg):
    async def scenario():
        db = FakeDB([_row()])
        client = _client(_response({"retrained": {"sensor-failure": "trained"}}))
        worker = _worker(cfg, db, client)

        fired = await worker._tick()
        await _await_retrain(worker)

        return db, client, worker, fired

    db, client, worker, fired = asyncio.run(scenario())

    assert fired == 1
    assert db.planned == [("daily-retrain", True)]
    call = _calls(client)[0]
    assert call["url"].endswith("/retrain")
    assert call["json"] == {"category": None}
    assert call["timeout"] == 5.0, "must use retrain_timeout_seconds"
    assert db.started == [(None, "run-1")]
    assert db.finished == [("run-1", "done", {"retrained": {"sensor-failure": "trained"}})]
    assert worker.stats["retrain_done"] == 1 and worker.stats["fired"] == 1


def test_category_comes_from_args(cfg):
    async def scenario():
        db = FakeDB([_row(args={"category": "fire-risk"})])
        client = _client()
        worker = _worker(cfg, db, client)
        await worker._tick()
        await _await_retrain(worker)
        return db, client

    db, client = asyncio.run(scenario())

    assert _calls(client)[0]["json"] == {"category": "fire-risk"}
    assert db.started == [("fire-risk", "run-1")]


def test_retrain_target_reports_unknown_args():
    job = ScheduleJob(
        id="1", kind="retrain", name="n", cron_expr="* * * * *",
        args={"category": "fire-risk", "categories": ["x"]},
    )
    assert SchedulerWorker._retrain_target(job) == ("fire-risk", ["categories"])
    empty = ScheduleJob(id="2", kind="retrain", name="n", cron_expr="* * * * *", args={})
    assert SchedulerWorker._retrain_target(empty) == (None, [])


# ---- failure handling ------------------------------------------------------


def test_all_failed_body_marks_the_run_failed(cfg):
    """`/retrain` answers 200 even when every category failed — trust the body."""

    async def scenario():
        db = FakeDB([_row()])
        client = _client(
            _response({"retrained": {"sensor-failure": {"state": "failed", "error": "no parquet"}}})
        )
        worker = _worker(cfg, db, client)
        await worker._tick()
        await _await_retrain(worker)
        return db, worker

    db, worker = asyncio.run(scenario())

    assert [r[1] for r in db.finished] == ["failed"]
    assert worker.stats["retrain_failed"] == 1 and worker.stats["retrain_done"] == 0


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"retrained": {"a": {"state": "failed"}}}, True),
        ({"retrained": {"a": {"state": "failed"}, "b": {"state": "failed"}}}, True),
        ({"retrained": {"a": {"state": "failed"}, "b": "trained"}}, False),
        ({"retrained": {"a": "trained"}}, False),
        ({"retrained": {}}, False),
        ({"other": 1}, False),
        ({}, False),
        ("nope", False),
        (None, False),
    ],
)
def test_all_failed(body, expected):
    assert _all_failed(body) is expected


def test_http_error_marks_failed_and_releases_the_slot(cfg):
    async def scenario():
        db = FakeDB([_row()])
        error = httpx.HTTPStatusError(
            "HTTP 503",
            request=httpx.Request("POST", "http://ml/retrain"),
            response=httpx.Response(503, request=httpx.Request("POST", "http://ml/retrain")),
        )
        worker = _worker(cfg, db, _client(error))
        await worker._tick()
        await _await_retrain(worker)
        return db, worker

    db, worker = asyncio.run(scenario())

    run_id, status, metrics = db.finished[0]
    assert run_id == "run-1" and status == "failed"
    assert "HTTPStatusError" in metrics["error"]
    assert worker.stats["retrain_failed"] == 1
    assert not worker._retrain_running(), "the next tick must be able to retrain again"


def test_transport_error_marks_failed(cfg):
    async def scenario():
        db = FakeDB([_row()])
        worker = _worker(cfg, db, _client(httpx.ConnectError("connection refused")))
        await worker._tick()
        await _await_retrain(worker)
        return db

    db = asyncio.run(scenario())
    assert db.finished[0][1] == "failed"
    assert "ConnectError" in db.finished[0][2]["error"]


def test_a_failed_retrain_does_not_stop_the_next_tick(cfg):
    async def scenario():
        db = FakeDB([_row()])
        # both occurrences fail: the client hands out one error per call
        worker = _worker(cfg, db, _client(httpx.ReadTimeout("a"), httpx.ReadTimeout("b")))
        await worker._tick()
        await _await_retrain(worker)
        second = await worker._tick()  # the fake reports the row as due again
        await _await_retrain(worker)
        return second, worker

    second, worker = asyncio.run(scenario())

    assert second == 1
    assert worker.stats["retrain_failed"] == 2


# ---- schedule semantics ----------------------------------------------------


def test_missed_job_is_skipped_and_rescheduled(cfg):
    """Down for an hour -> a daily retrain is NOT run late, just rescheduled."""

    async def scenario():
        db = FakeDB([_row(due_seconds_ago=3600)])
        worker = _worker(cfg, db, _client())
        fired = await worker._tick()
        return db, worker, fired

    db, worker, fired = asyncio.run(scenario())

    assert fired == 0 and db.started == []
    assert db.planned == [("daily-retrain", False)]
    assert worker.stats["skipped_missed"] == 1
    assert db.next_runs["daily-retrain"] > NOW, "next occurrence must be in the future"


def test_job_within_the_grace_window_runs(cfg):
    async def scenario():
        db = FakeDB([_row(due_seconds_ago=5)])
        worker = _worker(cfg, db, _client())
        fired = await worker._tick()
        await _await_retrain(worker)
        return fired, worker

    fired, worker = asyncio.run(scenario())

    assert fired == 1 and worker.stats["skipped_missed"] == 0


def test_never_scheduled_row_is_scheduled_not_run(cfg):
    async def scenario():
        db = FakeDB([_row(next_run_at=None, due_seconds_ago=None)])
        worker = _worker(cfg, db, _client())
        fired = await worker._tick()
        return db, worker, fired

    db, worker, fired = asyncio.run(scenario())

    assert fired == 0 and db.started == []
    assert db.next_runs["daily-retrain"] > NOW
    assert worker.stats["skipped_missed"] == 0


def test_unsupported_kind_is_advanced_and_never_called(cfg):
    async def scenario():
        db = FakeDB([_row(name="hourly-predict", kind="predict-all", cron="0 * * * *")])
        client = _client()
        worker = _worker(cfg, db, client)
        fired = await worker._tick()
        return db, client, worker, fired

    db, client, worker, fired = asyncio.run(scenario())

    assert fired == 0 and _calls(client) == []
    assert db.next_runs["hourly-predict"] > NOW, "still advanced so it stops being due"
    assert worker.stats["skipped_unsupported"] == 1


def test_unparseable_cron_is_logged_and_retried_tomorrow(cfg):
    async def scenario():
        db = FakeDB([_row(cron="not a cron")])
        client = _client()
        worker = _worker(cfg, db, client)
        fired = await worker._tick()
        return db, client, fired

    db, client, fired = asyncio.run(scenario())

    assert fired == 0 and _calls(client) == []
    nxt = db.next_runs["daily-retrain"]
    assert timedelta(hours=23) < nxt - NOW < timedelta(hours=25)


def test_expression_that_never_fires_does_not_wedge_the_tick(cfg):
    """31 February parses but never fires; the tick must survive it."""

    async def scenario():
        db = FakeDB([_row(cron="30 4 31 2 *")])
        worker = _worker(cfg, db, _client())
        fired = await worker._tick()
        return fired, db

    fired, db = asyncio.run(scenario())

    assert fired == 0
    assert ("daily-retrain", False) in db.planned


def test_second_retrain_is_skipped_while_one_is_in_flight(cfg):
    """Two due retrains in one tick: the second is skipped, not queued."""

    async def scenario():
        db = FakeDB([_row(name="retrain-a"), _row(name="retrain-b")])
        client = _client()
        worker = _worker(cfg, db, client)
        fired = await worker._tick()
        await _await_retrain(worker)
        return fired, worker, client, db

    fired, worker, client, db = asyncio.run(scenario())

    assert fired == 1, "only the first retrain may start"
    assert len(_calls(client)) == 1
    assert worker.stats["skipped_busy"] == 1
    assert db.started == [(None, "run-1")]


def test_disabled_rows_are_not_the_workers_business(cfg):
    """`enabled` is filtered in SQL; the worker must not run what it never sees."""

    async def scenario():
        db = FakeDB([])
        worker = _worker(cfg, db, _client())
        return await worker._tick(), worker

    fired, worker = asyncio.run(scenario())
    assert fired == 0
