"""Scheduler worker: executes due ``ml_schedule`` jobs.

Scope: **retrain only**. ``predict-all`` has no implementation — predictions are
driven by the journal fan-out and ``ml_predict_queue`` — and migration 039
disables the seeded ``hourly-predict`` row so it is never claimed. A claimed row
whose kind is not supported is advanced and logged, never executed, so a future
kind cannot silently wedge the scheduler.

Catch-up policy: a job due further in the past than
``SCHEDULER_MISSED_GRACE_SECONDS`` (we were down when it fired) is SKIPPED — its
next occurrence is scheduled and the miss is logged. A retrain is heavy and not
time-critical, so running a day-old one at startup is worse than waiting for the
next slot. A job with ``next_run_at IS NULL`` (never scheduled) is likewise
scheduled without running.

Concurrency: ``claim_due_jobs`` claims rows inside one transaction with
``FOR UPDATE SKIP LOCKED``, so two brokers never fire the same occurrence.

A retrain runs as a BACKGROUND task: it can take many minutes, and blocking the
tick loop for that long would push every other due row past the missed-run grace
window. Only one retrain runs at a time — a further due retrain is skipped with a
log line and picks up at its next occurrence — and the task is cancelled on
shutdown so the process still exits promptly.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime, timedelta, timezone

import httpx

from .config import Config
from .cron import CronError, next_after, parse
from .db import Db, ScheduleJob
from .log import get_logger

log = get_logger(__name__)

SUPPORTED_KINDS = ("retrain",)

# An unparseable cron_expr cannot be scheduled on its own merits; retry it
# daily so a fixed expression picks up within a day instead of every tick.
_BAD_CRON_RETRY = timedelta(days=1)


class SchedulerWorker:
    def __init__(self, db: Db, client: httpx.AsyncClient, cfg: Config) -> None:
        self._db = db
        self._client = client
        self._cfg = cfg
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._retrain_task: asyncio.Task[None] | None = None
        self._stats = {
            "ticks": 0,
            "fired": 0,
            "skipped_missed": 0,
            "skipped_unsupported": 0,
            "skipped_busy": 0,
            "retrain_done": 0,
            "retrain_failed": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="scheduler-worker")

    async def stop(self) -> None:
        """Stop and let the loop unwind.

        A retrain in flight is given a short grace period and then cancelled:
        the process must not hang on a 15-minute HTTP call. ml-service may still
        finish the training server-side — the run row matters for the history,
        and a run left 'running' by a hard exit is closed by the startup reaper
        (``Db.fail_stale_retrain_runs``).
        """
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                log.warning("scheduler stop timed out; cancelling the tick loop")
                self._task.cancel()
        if self._retrain_task and not self._retrain_task.done():
            log.warning("cancelling in-flight retrain")
            self._retrain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retrain_task

    async def _run(self) -> None:
        log.info(
            "scheduler worker started",
            poll_s=self._cfg.scheduler_poll_seconds,
            missed_grace_s=self._cfg.scheduler_missed_grace_seconds,
            kinds=list(SUPPORTED_KINDS),
        )
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._cfg.scheduler_poll_seconds
                )
                break  # stop was requested while waiting
            except asyncio.TimeoutError:
                pass
            self._stats["ticks"] += 1
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 — never kill the loop on a stray error
                log.exception("scheduler tick failed")

    async def _tick(self) -> int:
        """Claim due jobs (advancing their schedule) and dispatch them."""
        jobs = await self._db.claim_due_jobs(self._plan)
        fired = 0
        for job in jobs:
            if job.kind not in SUPPORTED_KINDS:
                # _plan is the gate; reaching here means the two disagree, which
                # must be loud rather than a silently dropped job.
                log.error("no handler for schedule kind", name=job.name, kind=job.kind)
                continue
            if self._retrain_running():
                self._stats["skipped_busy"] += 1
                log.warning(
                    "retrain still running; skipping this occurrence",
                    name=job.name,
                    next_run_at=_iso(job.next_run_at),
                )
                continue
            fired += 1
            self._stats["fired"] += 1
            task = asyncio.create_task(self._run_retrain(job), name=f"retrain-{job.name}")
            task.add_done_callback(_log_task_failure)
            self._retrain_task = task
        return fired

    def _retrain_running(self) -> bool:
        return self._retrain_task is not None and not self._retrain_task.done()

    def _plan(self, row: dict) -> tuple[datetime, bool]:
        """Decide the next occurrence of a claimed row and whether to run it.

        Called inside ``claim_due_jobs``'s transaction, so it must not await or
        block — it only parses the expression, logs and bumps counters. The
        returned ``next_run_at`` is persisted for this row either way, which is
        what makes a job stop being due even when it is skipped.
        """
        now = datetime.now(timezone.utc)
        name = row.get("name")
        try:
            cron = parse(row.get("cron_expr") or "")
            next_run = next_after(cron, now)
        except CronError as exc:
            # Both an unparseable expression and one that never fires land here.
            # Retry in a day so a corrected expression is picked up promptly
            # without log-spamming every poll, and never wedge the tick.
            log.error("unusable cron_expr, retrying tomorrow", name=name, error=str(exc))
            return now + _BAD_CRON_RETRY, False
        due_at = row.get("next_run_at")
        if due_at is None:
            log.info("schedule initialised", name=name, next_run_at=_iso(next_run))
            return next_run, False
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        if (now - due_at).total_seconds() > self._cfg.scheduler_missed_grace_seconds:
            self._stats["skipped_missed"] += 1
            log.warning(
                "missed schedule skipped",
                name=name,
                was_due_at=_iso(due_at),
                next_run_at=_iso(next_run),
            )
            return next_run, False
        if row.get("kind") not in SUPPORTED_KINDS:
            self._stats["skipped_unsupported"] += 1
            log.warning(
                "unsupported schedule kind skipped",
                name=name,
                kind=row.get("kind"),
                next_run_at=_iso(next_run),
            )
            return next_run, False
        return next_run, True

    async def _run_retrain(self, job: ScheduleJob) -> None:
        category, extra = self._retrain_target(job)
        if extra:
            log.warning("ignoring unsupported schedule args", name=job.name, keys=extra)
        payload = {"category": category}
        started = time.monotonic()
        run_id = await self._db.start_retrain_run(category)
        log.info("retrain started", name=job.name, run_id=run_id, category=category or "all")
        try:
            response = await self._client.post(
                f"{self._cfg.ml_base_url}/retrain",
                json=payload,
                timeout=self._cfg.retrain_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            # /retrain answers 200 even when a category failed: it reports the
            # failure per category in the body. Trust the body, not the status.
            status = "failed" if _all_failed(body) else "done"
            await self._db.finish_retrain_run(run_id, status, body)
            self._stats[f"retrain_{status}"] += 1
            log.info(
                "retrain finished",
                name=job.name,
                run_id=run_id,
                status=status,
                seconds=round(time.monotonic() - started, 1),
                result=body,
            )
        except Exception as exc:  # noqa: BLE001 — a failed retrain must not kill the loop
            self._stats["retrain_failed"] += 1
            error = f"{type(exc).__name__}: {exc}"
            await self._db.finish_retrain_run(run_id, "failed", {"error": error})
            log.error(
                "retrain failed",
                name=job.name,
                run_id=run_id,
                seconds=round(time.monotonic() - started, 1),
                error=error[:300],
            )

    @staticmethod
    def _retrain_target(job: ScheduleJob) -> tuple[str | None, list[str]]:
        """Read ``args`` into the /retrain payload; report unknown keys.

        ``POST /retrain`` takes a single optional ``category`` (null = all), so
        that is all a schedule may express. Anything else is surfaced instead of
        being silently dropped.
        """
        args = job.args if isinstance(job.args, dict) else {}
        raw = args.get("category")
        category = str(raw) if raw else None
        extra = sorted(key for key in args if key != "category")
        return category, extra


def _log_task_failure(task: asyncio.Task[None]) -> None:
    """Surface an unexpected crash of the retrain task (it catches its own errors)."""
    if task.cancelled():
        log.warning("retrain task cancelled")
        return
    exc = task.exception()
    if exc is not None:
        log.error("retrain task crashed", error=repr(exc))


def _all_failed(body: object) -> bool:
    """True when every category of a /retrain response reported a failure."""
    results = body.get("retrained") if isinstance(body, dict) else None
    if not isinstance(results, dict) or not results:
        return False
    return all(
        isinstance(value, dict) and value.get("state") == "failed"
        for value in results.values()
    )


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None
