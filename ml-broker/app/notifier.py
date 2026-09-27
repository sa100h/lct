"""NotifierWorker — dedicated LISTEN connection for forecast journals.

NOTIFY is fire-and-forget in Postgres: if nobody is listening when the
trigger fires, the event is lost. This worker keeps the listener alive and
reconnects on drop; the queue worker ALSO polls on a timer, so a missed
NOTIFY is never lost — this just makes it prompt.
"""

from __future__ import annotations

import asyncio

import asyncpg

from .config import Config
from .log import get_logger

log = get_logger(__name__)

RECONNECT_DELAY_SECONDS = 2.0


class NotifierWorker:
    def __init__(self, pool: asyncpg.Pool, cfg: Config, wake: asyncio.Event) -> None:
        self._pool = pool
        self._cfg = cfg
        self._wake = wake
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._conn: asyncpg.Connection | None = None
        self._connected = asyncio.Event()
        self._reconnect_count = 0

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def reconnects(self) -> int:
        return self._reconnect_count

    def request_stop(self) -> None:
        self._stop.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="notifier-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    async def _on_notify(self, conn, pid, channel, payload) -> None:
        log.debug("notify received", channel=channel, payload=payload)
        self._wake.set()  # idempotent: the drain loop is a no-op if the queue is empty

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                async with self._pool.acquire() as conn:
                    self._conn = conn
                    await conn.add_listener(self._cfg.forecast_listen_channel, self._on_notify)
                    self._connected.set()
                    self._reconnect_count += 1
                    log.info("LISTEN established", channel=self._cfg.forecast_listen_channel)
                    # Wait until the connection dies or we're told to stop.
                    stop = asyncio.create_task(self._wait_stop())
                    try:
                        while not self._stop.is_set():
                            await asyncio.sleep(0.2)
                    finally:
                        stop.cancel()
                    await conn.remove_listener(self._cfg.forecast_listen_channel, self._on_notify)
            except (asyncpg.PostgresError, OSError) as exc:
                self._connected.clear()
                log.warning("listener connection lost", error=str(exc))
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
            finally:
                self._connected.clear()
                if self._stop.is_set():
                    break
        self._conn = None

    async def _wait_stop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(0.2)
