"""Scheduler — crontab-like jobs from the ml_schedule table.

Kinds:
  predict-all  enqueue a queue row for every active subject (per category);
               the QueueWorker drains and persists.
  retrain      POST /retrain in a background asyncio task (long timeout —
               never blocks the predict queue), then log ml_retrain_runs.

Jobs are loaded from the DB at startup; last/next run timestamps are kept
in sync with the table.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import Db, ScheduleRow
from .log import get_logger

log = get_logger(__name__)


def _split_cron(expr: str) -> tuple[str, str, str, str, str]:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"expected 5-field cron, got: {expr!r}")
    return tuple(parts)  # type: ignore[return-value]


class Scheduler:
    def __init__(self, db: Db, client: httpx.AsyncClient, cfg: Config, wake: asyncio.Event) -> None:
        self._db = db
        self._client = client
        self._cfg = cfg
        self._wake = wake
        self._sched = AsyncIOScheduler(timezone="UTC")
        self._retrain_tasks: set[asyncio.Task[None]] = set()
        self._inflight_predict_all = False

    @property
    def apscheduler(self) -> AsyncIOScheduler:
        return self._sched

    async def start(self) -> None:
        jobs = [j for j in await self._db.load_schedule() if j.enabled]
        for job in jobs:
            try:
                trigger = CronTrigger.from_crontab(job.cron_expr)
            except ValueError:
                log.error("bad cron expression, job skipped", name=job.name, cron=job.cron_expr)
                continue
            self._sched.add_job(
                self._dispatch,
                trigger=trigger,
                id=f"{job.kind}:{job.name}",
                kwargs={"job": job},
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
            log.info("scheduled job", kind=job.kind, name=job.name, cron=job.cron_expr)
        self._sched.start()
        log.debug("scheduler started", jobs=len(jobs))

    async def stop(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)
        if self._retrain_tasks:
            await asyncio.gather(*self._retrain_tasks, return_exceptions=True)
        log.debug("scheduler stopped")

    async def _dispatch(self, job: ScheduleRow) -> None:
        now = datetime.now(timezone.utc)
        try:
            if job.kind == "predict-all":
                await self._predict_all(job)
            elif job.kind == "retrain":
                await self._retrain(job)
        except Exception:  # noqa: BLE001 — a job must never take down the scheduler
            log.exception("scheduled job failed", kind=job.kind, name=job.name)
        next_run = self._sched.get_job(f"{job.kind}:{job.name}").next_run_time if self._sched.get_job(f"{job.kind}:{job.name}") else None
        await self._db.touch_schedule(job.id, now, next_run)

    async def _predict_all(self, job: ScheduleRow) -> None:
        if self._inflight_predict_all:
            log.warning("predict-all skipped, previous run in flight")
            return
        self._inflight_predict_all = True
        try:
            categories = (job.args or {}).get("categories") or list(self._cfg.categories)
            subjects = await self._db.distinct_channels()
            if not subjects:
                log.info("predict-all: no subjects in sensor_features, nothing to enqueue")
                return
            inserted = await self._db.enqueue_subjects(subjects, categories)
            self._wake.set()
            log.info("predict-all enqueued", subjects=len(subjects), categories=categories, queue_rows=inserted)
        finally:
            self._inflight_predict_all = False

    async def _retrain(self, job: ScheduleRow) -> None:
        category: str | None = (job.args or {}).get("category")
        run_id = await self._db.log_retrain_start(category)
        task = asyncio.create_task(self._retrain_task(run_id, category), name="retrain")
        self._retrain_tasks.add(task)
        task.add_done_callback(self._retrain_tasks.discard)
        log.info("retrain started", run_id=run_id, category=category or "all")

    async def _retrain_task(self, run_id: str, category: str | None) -> None:
        try:
            resp = await self._client.post(
                f"{self._cfg.ml_base_url}/retrain",
                json={"category": category},
                timeout=self._cfg.retrain_timeout_seconds,
            )
            resp.raise_for_status()
            body = resp.json()
            await self._db.log_retrain_finish(run_id, "done", body)
            log.info("retrain done", run_id=run_id, body=body)
        except Exception as exc:  # noqa: BLE001 — record, don't propagate
            await self._db.log_retrain_finish(run_id, "failed", {"error": f"{type(exc).__name__}: {exc}"})
            log.error("retrain failed", run_id=run_id, error=str(exc))
