"""Logging setup (structlog; falls back cleanly if unavailable).

The five levels map onto stdlib: debug, info, warning, error, critical.
structlog aliases ``fatal`` -> ``critical`` (both emit ``level='critical'``).
The effective level is configurable via ``LOG_LEVEL`` (default ``INFO``);
pass an explicit name to :func:`configure` to override the environment.
"""

from __future__ import annotations

import logging
import os


def _resolve_level(name: str | None) -> int:
    """Map a LOG_LEVEL string (case-insensitive) to a stdlib level int.

    Unknown values fall back to INFO rather than crashing at startup.
    """
    if not name:
        return logging.INFO
    level = name.strip().upper()
    if level in ("FATAL", "CRITICAL"):
        return logging.CRITICAL
    for std in ("DEBUG", "INFO", "WARNING", "ERROR"):
        if level == std:
            return getattr(logging, std)
    return logging.INFO


try:
    import structlog

    def get_logger(name: str) -> structlog.stdlib.BoundLogger:
        return structlog.stdlib.get_logger(name)

    def configure(level: str | None = None) -> None:
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
        root.setLevel(_resolve_level(level if level else os.environ.get("LOG_LEVEL", "INFO")))

except ImportError:  # pragma: no cover — dev fallback
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

    def configure(level: str | None = None) -> None:
        logging.basicConfig(
            level=_resolve_level(level if level else os.environ.get("LOG_LEVEL", "INFO")),
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
