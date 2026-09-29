"""Environment-driven broker configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

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


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def dsn_to_kwargs(dsn: str) -> dict[str, Any]:
    """Normalize a DB_DSN into asyncpg.create_pool keyword arguments.

    asyncpg >= 0.31 dropped keyword-format DSNs ("host=... port=...") and
    only accepts a postgresql:// URI, while docker-compose / .env files
    historically use the keyword format. Convert both shapes to kwargs so
    create_pool never has to parse a DSN string at all.

    Precedence: explicit keyword params win over the URI components.
    """
    from urllib.parse import unquote, urlparse

    parts: dict[str, str] = {}
    rest = dsn
    if "://" in dsn:
        parsed = urlparse(dsn)
        rest = parsed.query
        if parsed.scheme not in ("postgres", "postgresql"):
            raise ValueError(
                f"unsupported DB_DSN scheme: {parsed.scheme!r} "
                "(expected postgresql:// or postgres://)"
            )
        if parsed.username:
            parts["user"] = unquote(parsed.username)
        if parsed.password is not None:
            parts["password"] = unquote(parsed.password)
        if parsed.hostname:
            parts["host"] = parsed.hostname
        if parsed.port:
            parts["port"] = str(parsed.port)
        if parsed.path and parsed.path != "/":
            parts["database"] = parsed.path.lstrip("/")
    # Keyword pairs may be space- or ampersand-separated (asyncpg accepts both);
    # a URI query string is already ampersand-separated.
    for chunk in rest.replace(" ", "&").split("&"):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        if key:
            parts[key] = value
    # asyncpg's DSN *string* accepted libpq's ``dbname=`` alias, but its
    # connect() kwarg is ``database`` — normalize so either source works.
    if "dbname" in parts:
        parts["database"] = parts.pop("dbname")
    if "password" in parts and parts["password"] == "":
        parts.pop("password")
    kwargs: dict[str, Any] = dict(parts)
    if "port" in kwargs:
        kwargs["port"] = int(kwargs["port"])
    return kwargs


@dataclass(frozen=True)
class Config:
    db_dsn: str = field(
        default_factory=lambda: os.environ.get(
            "DB_DSN",
            "postgresql://app_service:app_***@127.0.0.1:5432/app_db",
        )
    )
    ml_base_url: str = field(
        default_factory=lambda: os.environ.get("ML_BASE_URL", "http://127.0.0.1:8000")
    )
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
    # Automatic retraining from ml_schedule. Disable to run the broker as a
    # pure prediction consumer (the schedule rows stay untouched).
    scheduler_enabled: bool = field(
        default_factory=lambda: _env_bool("SCHEDULER_ENABLED", True)
    )
    # How often ml_schedule is polled for due rows. The seeded schedules are
    # hourly/daily, so this only bounds how late a job may start.
    scheduler_poll_seconds: float = field(
        default_factory=lambda: float(os.environ.get("SCHEDULER_POLL_SECONDS", "30"))
    )
    # A job due longer ago than this was missed while the broker was down: it is
    # skipped (not run late) and rescheduled. Cron expressions are interpreted
    # in UTC — the whole stack stores timestamptz.
    scheduler_missed_grace_seconds: float = field(
        default_factory=lambda: float(
            os.environ.get("SCHEDULER_MISSED_GRACE_SECONDS", "60")
        )
    )
    http_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))
    )
    # /predict_all_batch is inherently long: ONE call scores every subject of a
    # chunk across all four categories. The generic 30s HTTP timeout (health,
    # retrain, callbacks) is far too tight for that — a chunk of
    # FORECAST_BATCH_CHUNK=1000 subjects needs minutes on real history, so the
    # batch call gets its own, generous budget.
    predict_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("PREDICT_TIMEOUT_SECONDS", "600"))
    )
    health_host: str = field(default_factory=lambda: os.environ.get("HEALTH_HOST", "0.0.0.0"))
    health_port: int = field(default_factory=lambda: _env_int("HEALTH_PORT", 8080))
    horizon_hours: int = field(default_factory=lambda: _env_int("HORIZON_HOURS", 24))
    orphan_running_after_seconds: float = field(
        default_factory=lambda: float(os.environ.get("ORPHAN_RUNNING_AFTER_SECONDS", "600"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    # app-service callback (user login:password for Basic auth).
    app_service_callback_url: str = field(
        default_factory=lambda: os.environ.get(
            "APP_SERVICE_CALLBACK_URL", "http://app-service:8081/api/v1/forecasts/notify"
        )
    )
    app_service_login: str = field(default_factory=lambda: os.environ.get("APP_SERVICE_LOGIN", "lct"))
    app_service_password: str = field(default_factory=lambda: os.environ.get("APP_SERVICE_PASSWORD", ""))
    categories: tuple[str, ...] = _CATEGORIES
    forecast_listen_channel: str = field(
        default_factory=lambda: os.environ.get("FORECAST_LISTEN_CHANNEL", "lct_ml_forecast")
    )
    forecast_poll_seconds: float = field(
        default_factory=lambda: float(os.environ.get("FORECAST_POLL_SECONDS", "2"))
    )
    forecast_batch_chunk: int = field(default_factory=lambda: _env_int("FORECAST_BATCH_CHUNK", 300))
