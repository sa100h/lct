"""Queue worker for journal-driven forecast rows."""
from __future__ import annotations

import asyncio

import httpx

from .config import Config
from .db import Db, QueueRow
from .log import get_logger

log = get_logger(__name__)


class QueueWorker:
    def __init__(self, db: Db, client: httpx.AsyncClient, cfg: Config, wake: asyncio.Event) -> None:
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
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._cfg.poll_seconds)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                processed = await self._drain_once()
            except Exception:  # noqa: BLE001
                processed = 0
                log.exception("drain iteration failed")
            if processed == 0:
                self._stats["no_op_polls"] += 1

    async def _drain_once(self) -> int:
        """Claim a journal, fan it out, and drain a queue batch."""
        claim = getattr(self._db, "claim_open_journal", None)
        journal = await claim() if claim else None
        if journal:
            try:
                inserted = await self._db.fan_out_forecast(journal)
            except Exception as exc:  # noqa: BLE001
                await self._db.fail_journal(str(journal["id"]), str(exc))
                log.exception("forecast fan-out failed", journal_id=str(journal["id"]))
                inserted = 0
            else:
                log.info("forecast journal claimed", journal_id=str(journal["id"]), queue_rows=inserted)
                if inserted == 0:
                    await self._db.fail_journal(str(journal["id"]), "forecast_channels contains no known sensor channels")
        cancel = getattr(self._db, "cancel_open_journals", None)
        if cancel:
            await cancel()
        batch = await self._db.claim_batch(self._cfg.queue_batch)
        for row in batch:
            await self._process_row(row)
        return len(batch) + (1 if journal else 0)

    async def _process_row(self, row: QueueRow) -> None:
        attempts = row.attempts + 1
        try:
            result = await self._call_predict(row)
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            if 500 <= exc.response.status_code < 600 and attempts < self._cfg.max_attempts:
                await self._db.mark_retry(row.id, attempts, error, self._cfg.retry_backoff_seconds)
                self._stats["retried"] += 1
            else:
                await self._db.mark_failed(row.id, attempts, error)
                self._stats["failed"] += 1
                await self._finalize(row)
            return
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempts < self._cfg.max_attempts:
                await self._db.mark_retry(row.id, attempts, error, self._cfg.retry_backoff_seconds)
                self._stats["retried"] += 1
            else:
                await self._db.mark_failed(row.id, attempts, error)
                self._stats["failed"] += 1
                await self._finalize(row)
            return

        store = getattr(self._db, "store_result", None)
        if store:
            await store(row.id, result)
        await self._db.mark_done(row.id)
        self._stats["done"] += 1
        await self._finalize(row)

    async def _finalize(self, row: QueueRow) -> None:
        if row.forecast_journal_id:
            await self._db.finalize_journal(row.forecast_journal_id)

    async def _call_predict(self, row: QueueRow) -> dict:
        payload = {
            "category": row.category,
            "subject_id": row.subject_id,
            "current_features": row.features,
            "horizon_hours": self._cfg.horizon_hours,
        }
        response = await self._client.post(f"{self._cfg.ml_base_url}/predict", json=payload)
        response.raise_for_status()
        return response.json()
