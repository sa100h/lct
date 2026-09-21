from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    archive_path: Path
    cache_directory: Path
    source_start_at: datetime
    time_zone: ZoneInfo

    @classmethod
    def from_environment(cls) -> "Settings":
        time_zone = ZoneInfo(os.getenv("FEED_TIME_ZONE", "Europe/Moscow"))
        raw_start = os.getenv("FEED_SOURCE_START_AT", "2026-01-01T00:00:00")
        source_start_at = datetime.fromisoformat(raw_start)
        if source_start_at.tzinfo is None:
            source_start_at = source_start_at.replace(tzinfo=time_zone)
        else:
            source_start_at = source_start_at.astimezone(time_zone)

        return cls(
            archive_path=Path(os.getenv("FEED_ARCHIVE_PATH", "/data/ext-journal-2026.7z")),
            cache_directory=Path(os.getenv("FEED_CACHE_DIRECTORY", "/cache")),
            source_start_at=source_start_at,
            time_zone=time_zone,
        )

