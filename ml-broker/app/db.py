"""Database access for the journal-driven forecast broker."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import asyncpg

from .config import Config, dsn_to_kwargs
from .forecast_flow import (
    ML_BROKER_UUID,
    build_features,
    build_result_description,
    categories_for_sensor_type,
)
from .log import get_logger

log = get_logger(__name__)


def _as_features(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): val for key, val in value.items() if val is not None}


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


@dataclass
class QueueRow:
    id: int
    category: str
    subject_id: str
    as_of: datetime
    priority: int
    attempts: int
    features: dict[str, Any]
    forecast_journal_id: str | None = None
    forecast_name: str | None = None
    dispatcher_object_id: int | None = None


@dataclass
class ScheduleJob:
    """One due row of ``ml_schedule`` that the scheduler decided to run."""

    id: str
    kind: str
    name: str
    cron_expr: str
    args: dict[str, Any]
    next_run_at: datetime | None = None


class Db:
    def __init__(self, pool: asyncpg.Pool, cfg: Config) -> None:
        self._pool = pool
        self._cfg = cfg

    @staticmethod
    async def connect(dsn: str) -> asyncpg.Pool:
        pool = await asyncpg.create_pool(min_size=1, max_size=5, **dsn_to_kwargs(dsn))  # type: ignore[arg-type]
        log.debug("db pool ready")
        return pool

    async def close(self) -> None:
        await self._pool.close()

    async def requeue_orphans(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE ml_predict_queue SET status='pending', claimed_at=NULL
                   WHERE status='running' AND claimed_at < now() - make_interval(secs => $1)""",
                self._cfg.orphan_running_after_seconds,
            )
        return int(result.rsplit(" ", 1)[-1]) if result else 0

    async def claim_open_journal(self) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE forecast_journal
                       SET status='running', start_composition_time=COALESCE(start_composition_time, now())
                     WHERE id = (
                       SELECT id FROM forecast_journal
                        WHERE status='pending' AND NOT is_cancelled
                        ORDER BY creation_time, id
                        LIMIT 1 FOR UPDATE SKIP LOCKED
                     )
                     RETURNING *"""
                )
        return dict(row) if row else None

    async def fan_out_forecast(self, journal: dict[str, Any]) -> int:
        journal_id = str(journal["id"])
        channels = _json(journal.get("forecast_channels")) or {}
        if not isinstance(channels, dict):
            raise ValueError("forecast_channels must be a JSON object")
        creation_time = journal["creation_time"]
        if creation_time.tzinfo is None:
            creation_time = creation_time.replace(tzinfo=timezone.utc)
        creator = journal.get("user_created_id") or ML_BROKER_UUID
        forecast_name = f"{creation_time.strftime('%Y%m%dT%H%M%S')}_{creator}"
        keys = [str(k) for k in channels]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.id, c.sensor_type_id, c.dispatcher_object_id
                     FROM sensor_channels c WHERE c.id::text = ANY($1::text[])""",
                keys,
            ) if keys else []
            by_id = {str(r["id"]): r for r in rows}
            values: list[tuple[Any, ...]] = []
            for key, raw in channels.items():
                channel = by_id.get(str(key))
                if channel is None:
                    log.warning("forecast channel missing", journal_id=journal_id, channel_id=str(key))
                    continue
                for category in categories_for_sensor_type(channel["sensor_type_id"]):
                    values.append((
                        journal_id,
                        str(key),
                        category,
                        creation_time,
                        1,
                        forecast_name,
                        json.dumps(build_features(raw), ensure_ascii=False),
                        channel["dispatcher_object_id"],
                    ))
            if values:
                await conn.executemany(
                    """INSERT INTO ml_predict_queue
                       (forecast_journal_id, subject_id, category, as_of, priority,
                        forecast_name, features, dispatcher_object_id)
                       VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
                       ON CONFLICT (forecast_journal_id, subject_id, category, as_of) DO NOTHING""",
                    values,
                )
        return len(values)

    async def claim_batch(self, limit: int) -> list[QueueRow]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """SELECT id, category, subject_id, as_of, priority, attempts,
                              forecast_journal_id, forecast_name, features, dispatcher_object_id
                         FROM ml_predict_queue
                        WHERE status='pending' AND (retry_after IS NULL OR retry_after <= now())
                        ORDER BY forecast_journal_id NULLS LAST, priority DESC, id LIMIT $1 FOR UPDATE SKIP LOCKED""",
                    limit,
                )
                if rows:
                    await conn.execute(
                        "UPDATE ml_predict_queue SET status='running', claimed_at=now() WHERE id=ANY($1::bigint[])",
                        [r["id"] for r in rows],
                    )
        return [
            QueueRow(
                id=r["id"], category=r["category"], subject_id=r["subject_id"],
                as_of=r["as_of"], priority=r["priority"], attempts=r["attempts"],
                features=_as_features(r["features"]),
                forecast_journal_id=str(r["forecast_journal_id"]) if r["forecast_journal_id"] else None,
                forecast_name=r["forecast_name"], dispatcher_object_id=r["dispatcher_object_id"],
            )
            for r in rows
        ]

    async def store_result(self, row_id: int, result: dict[str, Any]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ml_predict_queue SET result=$2::jsonb WHERE id=$1 AND status='running'",
                row_id, json.dumps(result, default=str),
            )

    async def mark_done(self, row_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ml_predict_queue SET status='done', finished_at=now() WHERE id=$1 AND status='running'",
                row_id,
            )

    async def mark_retry(self, row_id: int, attempts: int, error: str, backoff_seconds: float) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE ml_predict_queue SET status='pending', attempts=$2, error=$3,
                   retry_after=now()+make_interval(secs=>$4), claimed_at=NULL WHERE id=$1 AND status='running'""",
                row_id, attempts, error, backoff_seconds,
            )

    async def mark_failed(self, row_id: int, attempts: int, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE ml_predict_queue SET status='failed', attempts=$2, error=$3,
                   finished_at=now(), claimed_at=NULL WHERE id=$1 AND status='running'""",
                row_id, attempts, error,
            )

    async def cancel_open_journals(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE forecast_journal SET status='cancelled', end_composition_time=now()
                   WHERE is_cancelled AND status IN ('pending','running')"""
            )
            await conn.execute(
                """UPDATE ml_predict_queue SET status='cancelled', error='cancelled',
                   finished_at=now(), claimed_at=NULL
                   WHERE forecast_journal_id IN (SELECT id FROM forecast_journal WHERE is_cancelled)
                     AND status IN ('pending','running')"""
            )
        return int(result.rsplit(" ", 1)[-1]) if result else 0

    async def fail_journal(self, journal_id: str, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE forecast_journal SET status='error', end_composition_time=now() WHERE id=$1",
                journal_id,
            )
            await conn.execute(
                """UPDATE ml_predict_queue SET status='failed', error=$2, finished_at=now(), claimed_at=NULL
                   WHERE forecast_journal_id=$1 AND status IN ('pending','running')""",
                journal_id, error,
            )

    async def finalize_journal(self, journal_id: str) -> None:
        async with self._pool.acquire() as conn:
            journal = await conn.fetchrow("SELECT * FROM forecast_journal WHERE id=$1", journal_id)
            if not journal:
                return
            if journal["is_cancelled"]:
                await conn.execute(
                    "UPDATE forecast_journal SET status='cancelled', end_composition_time=now() WHERE id=$1",
                    journal_id,
                )
                return
            counts = await conn.fetchrow(
                """SELECT count(*) FILTER (WHERE status IN ('pending','running')) AS open,
                          count(*) FILTER (WHERE status='failed') AS failed
                     FROM ml_predict_queue WHERE forecast_journal_id=$1""",
                journal_id,
            )
            if counts["open"] or counts["failed"]:
                if counts["failed"] and not counts["open"]:
                    await conn.execute(
                        "UPDATE forecast_journal SET status='error', end_composition_time=now() WHERE id=$1",
                        journal_id,
                    )
                return
            rows = await conn.fetch(
                """SELECT dispatcher_object_id, subject_id, category, result
                     FROM ml_predict_queue WHERE forecast_journal_id=$1 AND status='done'
                     ORDER BY dispatcher_object_id, subject_id, category""",
                journal_id,
            )
            grouped: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                result = _json(row["result"])
                if isinstance(result, dict) and row["dispatcher_object_id"] is not None:
                    result["subject_id"] = row["subject_id"]
                    result["category"] = row["category"]
                    grouped.setdefault(row["dispatcher_object_id"], []).append(result)
            creator = journal["user_created_id"] or ML_BROKER_UUID
            creation = journal["creation_time"]
            if creation.tzinfo is None:
                creation = creation.replace(tzinfo=timezone.utc)
            name = f"{creation.strftime('%Y%m%dT%H%M%S')}_{creator}"
            for object_id, predictions in grouped.items():
                await conn.execute(
                    """INSERT INTO forecast_results
                       (forecast_journal_id, forecast_name, forecast_description,
                        dispatcher_object_id, user_dispatcher_id, is_erroneous, is_cancelled)
                       VALUES ($1,$2,$3::jsonb,$4,$5,false,false)
                       ON CONFLICT (forecast_journal_id, dispatcher_object_id) DO UPDATE SET
                         forecast_name=EXCLUDED.forecast_name,
                         forecast_description=EXCLUDED.forecast_description,
                         user_dispatcher_id=EXCLUDED.user_dispatcher_id,
                         is_erroneous=false, is_cancelled=false, created_at=now()""",
                    journal_id, name,
                    json.dumps(build_result_description(predictions, creation), ensure_ascii=False),
                    object_id, ML_BROKER_UUID,
                )
            await conn.execute(
                "UPDATE forecast_journal SET status='done', end_composition_time=now() WHERE id=$1",
                journal_id,
            )

    # ---- ml_schedule: the automatic retrain driver --------------------------

    async def claim_due_jobs(
        self, plan: Callable[[dict[str, Any]], tuple[datetime, bool]]
    ) -> list[ScheduleJob]:
        """Claim every due schedule row, in one transaction.

        ``FOR UPDATE SKIP LOCKED`` combined with doing the update in the same
        transaction is what keeps two broker replicas from firing the same
        occurrence. ``plan`` decides each row's next occurrence and whether it
        should run (missed jobs and unsupported kinds are advanced without
        running); ``last_run_at`` is only touched for rows that actually run.
        """
        jobs: list[ScheduleJob] = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """SELECT id, kind, name, cron_expr, args, last_run_at, next_run_at
                         FROM ml_schedule
                        WHERE enabled AND (next_run_at IS NULL OR next_run_at <= now())
                        ORDER BY next_run_at NULLS FIRST, name
                          FOR UPDATE SKIP LOCKED"""
                )
                updates: list[tuple[Any, ...]] = []
                for row in rows:
                    next_run, fire = plan(dict(row))
                    updates.append((row["id"], next_run, fire))
                    if fire:
                        jobs.append(
                            ScheduleJob(
                                id=str(row["id"]),
                                kind=row["kind"],
                                name=row["name"],
                                cron_expr=row["cron_expr"],
                                args=_json(row["args"]) or {},
                                next_run_at=next_run,
                            )
                        )
                if updates:
                    await conn.executemany(
                        """UPDATE ml_schedule
                              SET next_run_at = $2,
                                  last_run_at = CASE WHEN $3 THEN now() ELSE last_run_at END
                            WHERE id = $1""",
                        updates,
                    )
        return jobs

    async def start_retrain_run(self, category: str | None) -> str:
        """Open a ``ml_retrain_runs`` row (status 'running'); returns its id."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO ml_retrain_runs (category, status)
                   VALUES ($1, 'running') RETURNING id""",
                category,
            )
        return str(row["id"])

    async def finish_retrain_run(self, run_id: str, status: str, metrics: dict[str, Any]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE ml_retrain_runs SET finished_at=now(), status=$2, metrics=$3::jsonb
                    WHERE id=$1 AND status='running'""",
                run_id, status, json.dumps(metrics, default=str),
            )

    async def fail_stale_retrain_runs(self, older_than_seconds: float) -> int:
        """Close runs left 'running' by a restart (mirrors requeue_orphans).

        Without this, killing the broker mid-retrain would leave a row running
        forever and the history in ``ml_retrain_runs`` would lie.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE ml_retrain_runs
                      SET status='failed', finished_at=now(),
                          metrics=COALESCE(metrics, '{}'::jsonb)
                                  || jsonb_build_object('error',
                                       'abandoned: broker restarted while running')
                    WHERE status='running'
                      AND started_at < now() - make_interval(secs => $1)""",
                older_than_seconds,
            )
        return int(result.rsplit(" ", 1)[-1]) if result else 0
