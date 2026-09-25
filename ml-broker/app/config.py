"""Environment-driven broker configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_CATEGORIES = (
    "sensor-failure",
    "fire-risk",
    "unauthorized-access",
    "infrastructure-wear",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    db_dsn: str = field(
        default_factory=lambda: os.environ.get(
            "DB_DSN",
            "host=127.0.0.1 port=5432 dbname=app_db user=app_service password=app_dev",
        )
    )
    ml_base_url: str = field(
        default_factory=lambda: os.environ.get("ML_BASE_URL", "http://127.0.0.1:8000")
    )
    queue_batch: int = field(default_factory=lambda: _env_int("QUEUE_BATCH", 10))
    poll_seconds: float = field(
        default_factory=lambda: float(os.environ.get("POLL_SECONDS", "5"))
    )
    max_attempts: int = field(default_factory=lambda: _env_int("MAX_ATTEMPTS", 3))
    retry_backoff_seconds: float = field(
        default_factory=lambda: float(os.environ.get("RETRY_BACKOFF_SECONDS", "10"))
    )
    retrain_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("RETRAIN_TIMEOUT_SECONDS", "900"))
    )
    http_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))
    )
    health_host: str = field(default_factory=lambda: os.environ.get("HEALTH_HOST", "0.0.0.0"))
    health_port: int = field(default_factory=lambda: _env_int("HEALTH_PORT", 8080))
    horizon_hours: int = field(default_factory=lambda: _env_int("HORIZON_HOURS", 24))
    orphan_running_after_seconds: float = field(
        default_factory=lambda: float(os.environ.get("ORPHAN_RUNNING_AFTER_SECONDS", "600"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    categories: tuple[str, ...] = _CATEGORIES
    listen_channel: str = field(default_factory=lambda: os.environ.get("LISTEN_CHANNEL", "ml_predict"))
