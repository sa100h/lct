"""Postgres access layer for the ml-broker.

The durable queue (``ml_predict_queue``) is the source of truth; this module
only ever moves rows through pending -> running -> done|failed and persists
results into ``predictions``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .config import Config
from .log import get_logger

log = get_logger(__name__)


def _as_features(value: Any) -> dict[str, float]:
    """Normalize a jsonb features column (dict, JSON string, or None) to a float dict."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in value.items():
        try:
            out[str(key)] = float(val)
        except (ValueError, TypeError):
            continue
    return out


@dataclass
class QueueRow:
    id: int
    category: str
    subject_id: str
    as_of: datetime
    priority: int
    attempts: int
    features: dict[str, float]


@dataclass
class ScheduleRow:
    id: str
    kind: str
    name: str
    cron_expr: str
    args: dict[str, Any]
    enabled: bool


class Db:
    def __init__(self, pool: asyncpg.Pool, cfg: Config) -> None:
        self._pool = pool
        self._cfg = cfg

    @staticmethod
    async def connect(dsn: str) -> asyncpg.Pool:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        log.debug("db pool ready")
        return pool

    async def close(self) -> None:
        await self._pool.close()
        log.debug("db pool closed")

    # -- startup -----------------------------------------------------------------

    async def requeue_orphans(self) -> int:
        """Re-pend rows a crashed broker left mid-claim. Returns count recovered."""
        async with self._pool.acquire() as conn:
            res = await conn.execute(
                """
                UPDATE ml_predict_queue
                   SET status = 'pending', claimed_at = NULL
                 WHERE status = 'running'
                   AND claimed_at < now() - make_interval(secs => $1)
                """,
                self._cfg.orphan_running_after_seconds,
            )
        recovered = int(res.rsplit(" ", 1)[-1]) if res else 0
        log.debug("orphan scan", requeued=recovered)
        return recovered

    # -- queue -------------------------------------------------------------------

    async def claim_batch(self, limit: int) -> list[QueueRow]:
        """Atomically claim up to ``limit`` oldest pending rows (oldest first)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT q.id, q.category, q.subject_id, q.as_of, q.priority, q.attempts, f.features
                      FROM ml_predict_queue q
                     LEFT JOIN LATERAL (
                          SELECT s.features
                            FROM sensor_features s
                           WHERE s.channel_id = q.subject_id
                             AND s.as_of = q.as_of
                           LIMIT 1
                        ) f ON TRUE
                     WHERE q.status = 'pending'
                       AND (q.retry_after IS NULL OR q.retry_after <= now())
                     ORDER BY q.priority DESC, q.id ASC
                     LIMIT $1
                     FOR UPDATE OF q SKIP LOCKED
                    """,
                    limit,
                )
                if rows:
                    ids = [r["id"] for r in rows]
                    await conn.execute(
                        "UPDATE ml_predict_queue SET status = 'running', claimed_at = now() WHERE id = ANY($1)",
                        ids,
                    )
        return [
            QueueRow(
                id=r["id"],
                category=r["category"],
                subject_id=r["subject_id"],
                as_of=r["as_of"],
                priority=r["priority"],
                attempts=r["attempts"],
                features=_as_features(r["features"]),
            )
            for r in rows
        ]

    async def mark_done(self, row_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ml_predict_queue SET status = 'done', finished_at = now() WHERE id = $1",
                row_id,
            )

    async def mark_retry(self, row_id: int, attempts: int, error: str, backoff_seconds: float) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ml_predict_queue
                   SET status = 'pending',
                       attempts = $2,
                       error = $3,
                       retry_after = now() + make_interval(secs => $4),
                       claimed_at = NULL
                 WHERE id = $1
                """,
                row_id,
                attempts,
                error,
                backoff_seconds,
            )

    async def mark_failed(self, row_id: int, attempts: int, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ml_predict_queue
                   SET status = 'failed', attempts = $2, error = $3, finished_at = now(), claimed_at = NULL
                 WHERE id = $1
                """,
                row_id,
                attempts,
                error,
            )

    # -- results ------------------------------------------------------------------

    async def upsert_prediction(
        self,
        *,
        category: str,
        subject_id: str,
        risk_score: float,
        predicted_label: bool,
        horizon_hours: int,
        model_version: str | None,
        predicted_at: datetime,
        feature_importance: dict[str, float] | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO predictions
                    (category, subject_id, risk_score, predicted_label, horizon_hours,
                     model_version, predicted_at, feature_importance)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                ON CONFLICT (category, subject_id, predicted_at)
                DO UPDATE SET
                    risk_score = EXCLUDED.risk_score,
                    predicted_label = EXCLUDED.predicted_label,
                    horizon_hours = EXCLUDED.horizon_hours,
                    model_version = EXCLUDED.model_version,
                    feature_importance = EXCLUDED.feature_importance
                """,
                category,
                subject_id,
                round(float(risk_score), 4),
                predicted_label,
                horizon_hours,
                model_version,
                predicted_at.astimezone(timezone.utc) if predicted_at.tzinfo else predicted_at.replace(tzinfo=timezone.utc),
                json.dumps(feature_importance or {}),
            )

    async def reenqueue(self, row_id: int, attempts: int, error: str, backoff_seconds: float) -> None:
        """Alias kept for readability at call sites (== mark_retry)."""
        await self.mark_retry(row_id, attempts, error, backoff_seconds)

    # -- scheduler table -----------------------------------------------------------

    async def distinct_channels(self) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT channel_id FROM sensor_features")
        return [r["channel_id"] for r in rows]

    async def enqueue_subjects(self, subjects: list[str], categories: list[str]) -> int:
        """Enqueue (subject, category) pairs at each subject's latest as_of. Dedup-safe."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for subject in subjects:
                    for cat in categories:
                        await conn.execute(
                            """
                            INSERT INTO ml_predict_queue (category, subject_id, as_of)
                            VALUES ($1, $2, (SELECT max(as_of) FROM sensor_features WHERE channel_id = $2))
                            ON CONFLICT (category, subject_id, as_of) DO NOTHING
                            """,
                            cat,
                            subject,
                        )
        return len(subjects) * len(categories)

    async def load_schedule(self) -> list[ScheduleRow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM ml_schedule ORDER BY kind, name")
        log.debug("schedule loaded", jobs=len(rows))
        return [
            ScheduleRow(
                id=str(r["id"]),
                kind=r["kind"],
                name=r["name"],
                cron_expr=r["cron_expr"],
                args=json.loads(r["args"]) if isinstance(r["args"], (str, bytes)) else dict(r["args"]),
                enabled=r["enabled"],
            )
            for r in rows
        ]

    async def touch_schedule(self, schedule_id: str, last_run_at: datetime, next_run_at: datetime | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ml_schedule SET last_run_at = $2, next_run_at = $3 WHERE id = $1",
                schedule_id,
                last_run_at,
                next_run_at,
            )

    # -- retrain log ---------------------------------------------------------------

    async def log_retrain_start(self, category: str | None) -> str:
        async with self._pool.acquire() as conn:
            run_id = await conn.fetchval(
                "INSERT INTO ml_retrain_runs (category, status) VALUES ($1, 'running') RETURNING id",
                category,
            )
        return str(run_id)

    async def log_retrain_finish(self, run_id: str, status: str, metrics: dict[str, Any]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ml_retrain_runs SET status = $2, finished_at = now(), metrics = $3::jsonb WHERE id = $1",
                run_id,
                status,
                json.dumps(metrics, default=str),
            )
