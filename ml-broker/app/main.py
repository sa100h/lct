"""ml-broker entrypoint.

One asyncio process:
  - Db pool + orphan recovery
  - NotifierWorker (LISTEN lct_ml_forecast -> wake)
  - QueueWorker (journal -> queue -> /predict_all_batch -> forecast_results)
  - tiny HTTP server with /healthz on HEALTH_PORT

Graceful shutdown on SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import datetime, timezone

import httpx

from .config import Config, dsn_to_kwargs
from .db import Db
from .log import configure, get_logger
from .notifier import NotifierWorker
from .queue_worker import QueueWorker


log = get_logger(__name__)

STATE: dict[str, object] = {"status": "starting"}


async def main() -> None:
    cfg = Config()
    configure(cfg.log_level)
    wake = asyncio.Event()
    conn = dsn_to_kwargs(cfg.db_dsn)
    log.info(
        "ml-broker starting",
        db=f"host={conn.get('host')}:{conn.get('port')} db={conn.get('database')} user={conn.get('user')}",
        ml=cfg.ml_base_url,
        health=f"{cfg.health_host}:{cfg.health_port}",
        level=cfg.log_level,
    )

    try:
        pool = await Db.connect(cfg.db_dsn)
    except Exception as exc:  # noqa: BLE001 — DB is mandatory; can't start without it
        log.fatal("db connection failed, cannot start", error=repr(exc))
        raise
    db = Db(pool, cfg)
    recovered = await db.requeue_orphans()
    if recovered:
        log.info("orphan recovery", requeued=recovered)

    client = httpx.AsyncClient(timeout=cfg.http_timeout_seconds)
    notifier = NotifierWorker(pool, cfg, wake)
    worker = QueueWorker(db, client, cfg, wake)


    health = HealthServer(cfg.health_host, cfg.health_port, worker, notifier)
    try:
        await health.start()
    except OSError as exc:
        log.fatal("health server failed to bind", host=cfg.health_host, port=cfg.health_port, error=repr(exc))
        await db.close()
        raise

    async with client:
        await notifier.start()
        await worker.start()

        STATE["status"] = "running"
        log.info("ml-broker running")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()

    log.info("shutting down")
    await worker.stop()

    await notifier.stop()
    await health.stop()
    await db.close()
    STATE["status"] = "stopped"
    log.info("stopped")


class HealthServer:
    """Minimal asyncio HTTP server exposing /healthz and /stats."""

    def __init__(self, host: str, port: int, worker: QueueWorker, notifier: NotifierWorker) -> None:
        self._host = host
        self._port = port
        self._worker = worker
        self._notifier = notifier
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self._host, self._port)
        log.info("health server listening", host=self._host, port=self._port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            # drain the rest of the request head (we ignore the body)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
            path = request_line.split(b" ")[1].decode() if b" " in request_line else ""
            if path == "/healthz":
                body = b'{"status":"ok"}'
                status, reason = 200, "OK"
            elif path == "/stats":
                import json

                body = (
                    json.dumps(
                        {
                            "status": STATE.get("status"),
                            "queue": self._worker.stats,
                            "notifier_connected": self._notifier.connected,
                            "notifier_reconnects": self._notifier.reconnects,
                            "now": datetime.now(timezone.utc).isoformat(),
                        }
                    ).encode()
                )
                status, reason = 200, "OK"
            else:
                body = b"not found"
                status, reason = 404, "Not Found"
                log.warning("health unknown path", path=path)
            resp = (
                f"HTTP/1.1 {status} {reason}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode() + body
            writer.write(resp)
            await writer.drain()
        except asyncio.TimeoutError:
            log.debug("health request timed out")
        except (ConnectionError, OSError):
            # client went away before/while we responded — benign
            log.debug("health request dropped")
        except Exception:  # noqa: BLE001 - surface unexpected handler errors
            log.warning("health request failed", exc_info=True)
        finally:
            writer.close()


if __name__ == "__main__":
    asyncio.run(main())
