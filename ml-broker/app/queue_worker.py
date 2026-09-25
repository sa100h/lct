"""QueueWorker — the only consumer of ml_predict_queue.

Wake sources: NOTIFY poke (event) OR the poll timer (backstop — NOTIFY is
fire-and-forget, the DB is the source of truth). At-least-once delivery:
claim -> call /predict -> upsert predictions -> done; on error retry with
backoff up to MAX_ATTEMPTS, then failed. Dedup key (category, subject_id,
as_of) in the DB + ON CONFLICT in predictions makes replays idempotent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from .config import Config
from .db import Db, QueueRow
from .log import get_logger

log = get_logger(__name__)


class QueueWorker:
    def __init__(
        self,
        db: Db,
        client: httpx.AsyncClient,
        cfg: Config,
        wake: asyncio.Event,
    ) -> None:
        self._db = db
        self._client = client
        self._cfg = cfg
        self._wake = wake
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stats = {"done": 0, "failed": 0, "retried": 0, "no_op_polls": 0}

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def request_stop(self) -> None:
        self._stop.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="queue-worker")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task:
            await asyncio.wait_for(self._task, timeout=10)

    async def _run(self) -> None:
        log.info("queue worker started", batch=self._cfg.queue_batch, poll_s=self._cfg.poll_seconds)
        while not self._stop.is_set():
            # Wait for NOTIFY poke or poll timeout — whichever comes first.
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._cfg.poll_seconds)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            processed = 0
            try:
                processed = await self._drain_once()
            except Exception:  # noqa: BLE001 — never kill the loop on a stray error
                log.exception("drain iteration failed")
            if processed == 0:
                self._stats["no_op_polls"] += 1
                log.debug("drain no-op, queue empty", no_op_polls=self._stats["no_op_polls"])

    async def _drain_once(self) -> int:
        """Claim a batch and process every row. Returns rows processed."""
        batch = await self._db.claim_batch(self._cfg.queue_batch)
        if not batch:
            return 0
        log.info("claimed batch", size=len(batch), ids=[r.id for r in batch])
        for row in batch:
            await self._process_row(row)
        return len(batch)

    async def _process_row(self, row: QueueRow) -> None:
        attempts = row.attempts + 1  # this attempt
        result = None
        err: str | None = None
        try:
            result = await self._call_predict(row)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 500 <= status < 600:
                # Retryable server error — route through mark_retry/mark_failed
                # (a bare `raise` would strand the row `running`: claim_batch
                # only takes `pending` and requeue_orphans runs at startup).
                err = f"HTTP {status}: {exc.response.text[:300]}"
                log.warning("predict 5xx", id=row.id, status=status, body=exc.response.text[:300])
            else:
                # 4xx = the request itself is wrong; retrying will not fix it.
                self._stats["failed"] += 1
                await self._db.mark_failed(row.id, attempts, f"HTTP {status}: {exc.response.text[:300]}")
                log.error("predict rejected", id=row.id, status=status, body=exc.response.text[:300])
                return
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            err = f"{type(exc).__name__}: {exc}"

        if result is not None:
            await self._persist_prediction(row, result)
            await self._db.mark_done(row.id)
            self._stats["done"] += 1
            log.info("predict done", id=row.id, subject=row.subject_id, category=row.category)
            return

        if attempts < self._cfg.max_attempts:
            await self._db.mark_retry(row.id, attempts, err or "unknown error", self._cfg.retry_backoff_seconds)
            self._stats["retried"] += 1
            log.warning("predict failed, will retry", id=row.id, attempt=attempts, error=err)
        else:
            await self._db.mark_failed(row.id, attempts, err or "unknown error")
            self._stats["failed"] += 1
            log.error("predict failed permanently", id=row.id, error=err)

    async def _call_predict(self, row: QueueRow) -> dict:
        payload = {
            "category": row.category,
            "subject_id": row.subject_id,
            "current_features": row.features,
            "horizon_hours": self._cfg.horizon_hours,
        }
        resp = await self._client.post(f"{self._cfg.ml_base_url}/predict", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def _persist_prediction(self, row: QueueRow, result: dict) -> None:
        predicted_at = result.get("predicted_at")
        if isinstance(predicted_at, str):
            predicted_at = datetime.fromisoformat(predicted_at.replace("Z", "+00:00"))
        elif not isinstance(predicted_at, datetime):
            predicted_at = datetime.now(timezone.utc)
        await self._db.upsert_prediction(
            category=row.category,
            subject_id=row.subject_id,
            risk_score=float(result["risk_score"]),
            predicted_label=bool(result["predicted_label"]),
            horizon_hours=int(result.get("horizon_hours", self._cfg.horizon_hours)),
            model_version=result.get("model_version"),
            predicted_at=predicted_at,
            feature_importance=result.get("feature_importance") or {},
        )
