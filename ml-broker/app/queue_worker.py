"""Queue worker: journal fan-out + chunked /predict_all_batch drain."""
from __future__ import annotations

import asyncio
import time

import httpx

from .config import Config
from .db import Db, QueueRow
from .forecast_flow import PredictChunk, build_chunks
from .log import get_logger

log = get_logger(__name__)

# A batch call that exceeds PREDICT_TIMEOUT_SECONDS is assumed to be too big
# rather than broken: it is split in half and retried, down to this floor.
# Below the floor a timeout is a real service problem -> normal retry path.
MIN_SPLIT_SUBJECTS = 25


class QueueWorker:
    def __init__(self, db: Db, client: httpx.AsyncClient, cfg: Config, wake: asyncio.Event) -> None:
        self._db = db
        self._client = client
        self._cfg = cfg
        self._wake = wake
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._idle = True
        self._stats = {"done": 0, "failed": 0, "retried": 0, "no_op_polls": 0, "batch_calls": 0}

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
        log.info(
            "queue worker started",
            chunk_subjects=self._cfg.forecast_batch_chunk,
            poll_s=self._cfg.poll_seconds,
        )
        while not self._stop.is_set():
            self._wake.clear()
            if self._idle:
                # Nothing to do last tick: wait for a NOTIFY poke or the poll timer.
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self._cfg.poll_seconds)
                except asyncio.TimeoutError:
                    pass
            if self._stop.is_set():
                break
            try:
                processed = await self._drain_once()
            except Exception:  # noqa: BLE001 — never kill the loop on a stray error
                processed = 0
                log.exception("drain iteration failed")
                self._idle = True
            if self._idle:
                self._stats["no_op_polls"] += 1

    async def _drain_once(self) -> int:
        """Claim a journal, fan it out, and drain queue rows in batch chunks."""
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
        rows = await self._db.claim_batch(self._claim_rows())
        processed = 0
        for chunk in build_chunks(rows, self._cfg.forecast_batch_chunk):
            processed += await self._process_chunk(chunk)
        # Track productivity at the source: _run consults this to decide
        # whether to wait (idle) or immediately drain the next batch.
        self._idle = processed == 0 and journal is None
        return processed + (1 if journal else 0)

    def _claim_rows(self) -> int:
        # Rows per claim: every claimed subject needs one row per category.
        return max(1, self._cfg.forecast_batch_chunk * len(self._cfg.categories))

    async def _process_chunk(self, chunk: PredictChunk, depth: int = 0) -> int:
        """One POST /predict_all_batch for the whole chunk.

        A timeout does NOT burn an attempt: an oversized chunk is split in half
        and both halves are retried (recursively, down to MIN_SPLIT_SUBJECTS).
        That keeps a too-large FORECAST_BATCH_CHUNK from stalling a whole
        journal on a service that is merely slower than the timeout.
        """
        payload = {
            "subject_ids": chunk.subjects,
            "current_features": chunk.features,
            "horizon_hours": self._cfg.horizon_hours,
            "as_of": chunk.as_of.isoformat(),
        }
        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{self._cfg.ml_base_url}/predict_all_batch",
                json=payload,
                timeout=self._cfg.predict_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            log.warning("predict_all_batch http error", size=len(chunk.rows), error=error[:120])
            return await self._fail_chunk(chunk, error, retryable=500 <= exc.response.status_code < 600)
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - started
            error = f"{type(exc).__name__}: {exc}"
            if len(chunk.subjects) > MIN_SPLIT_SUBJECTS:
                log.warning(
                    "predict_all_batch timed out, splitting chunk",
                    subjects=len(chunk.subjects),
                    seconds=round(elapsed, 1),
                    timeout=self._cfg.predict_timeout_seconds,
                    depth=depth,
                )
                return await self._split_chunk(chunk, depth)
            log.warning(
                "predict_all_batch timeout at floor size",
                size=len(chunk.rows),
                seconds=round(elapsed, 1),
                error=error[:120],
            )
            return await self._fail_chunk(chunk, error, retryable=True)
        except httpx.TransportError as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.warning("predict_all_batch transport error", size=len(chunk.rows), error=error[:120])
            return await self._fail_chunk(chunk, error, retryable=True)

        subject_results = body.get("predictions", []) if isinstance(body, dict) else []
        done = await self._spread(chunk, subject_results)
        self._stats["done"] += done
        self._stats["batch_calls"] += 1
        log.info(
            "predict_all_batch ok",
            subjects=len(chunk.subjects),
            rows=len(chunk.rows),
            seconds=round(time.monotonic() - started, 1),
        )
        return done

    async def _split_chunk(self, chunk: PredictChunk, depth: int) -> int:
        """Halve an oversized chunk and process the halves (no attempt penalty)."""
        half = max(1, len(chunk.subjects) // 2)
        done = 0
        for part in build_chunks(chunk.rows, half):
            if len(part.subjects) >= len(chunk.subjects):  # cannot shrink further
                done += await self._fail_chunk(
                    part, f"timeout with {len(part.subjects)} subjects after split", retryable=True
                )
                continue
            done += await self._process_chunk(part, depth + 1)
        return done

    async def _spread(self, chunk: PredictChunk, subject_results: list[dict]) -> int:
        """Map the batch response back onto this chunk's queue rows."""
        by_key = {(r.subject_id, r.category): r for r in chunk.rows}
        handled = 0
        for entry in subject_results:
            subject = str(entry.get("subject_id"))
            for pred in entry.get("predictions", []):
                row = by_key.get((subject, str(pred.get("category"))))
                if row is None:
                    continue  # not our chunk's (subject, category)
                if "applicable" in pred:
                    applicable = bool(pred["applicable"])
                else:
                    # ml-service omits `applicable` when applicable=True
                    # (Prediction schema has no such field) — a prediction body
                    # present means scored; missing/None means not applicable.
                    applicable = pred.get("prediction") is not None or "risk_score" in pred
                if applicable:
                    await self._db.store_result(row.id, pred.get("prediction") or pred)
                else:
                    await self._db.store_result(
                        row.id,
                        {
                            "applicable": False,
                            "category": pred.get("category"),
                            "subject_id": subject,
                        },
                    )
                await self._db.mark_done(row.id)
                await self._finalize(row)
                handled += 1
        return handled

    async def _fail_chunk(self, chunk: PredictChunk, error: str, retryable: bool) -> int:
        """5xx/timeout -> whole chunk back to pending with backoff; else failed."""
        handled = 0
        for row in chunk.rows:
            attempts = row.attempts + 1
            if retryable and attempts < self._cfg.max_attempts:
                await self._db.mark_retry(row.id, attempts, error, self._cfg.retry_backoff_seconds)
                self._stats["retried"] += 1
            else:
                await self._db.mark_failed(row.id, attempts, error)
                self._stats["failed"] += 1
            await self._finalize(row)
            handled += 1
        return handled

    async def _finalize(self, row: QueueRow) -> None:
        if row.forecast_journal_id:
            await self._db.finalize_journal(row.forecast_journal_id)
