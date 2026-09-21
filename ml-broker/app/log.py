"""Logging setup (structlog; falls back cleanly if unavailable)."""

from __future__ import annotations

import logging

try:
    import structlog

    def get_logger(name: str) -> structlog.stdlib.BoundLogger:
        return structlog.stdlib.get_logger(name)

    def configure() -> None:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        handler = logging.StreamHandler()
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=[
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                ],
                processor=structlog.processors.KeyValueRenderer(key_order=["event"]),
            )
        )
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)

except ImportError:  # pragma: no cover — dev fallback
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

    def configure() -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
