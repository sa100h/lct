from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import uuid
from collections import OrderedDict
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, TextIO

from app.models import EventDto, EventPage, FeedStatus
from app.settings import Settings

EXPECTED_COLUMNS = [
    "ид_события",
    "ид_канала_данных",
    "дата",
    "время",
    "тревожное",
    "значение_датчика",
]
TRUE_VALUES = {"1", "t", "true", "yes"}
LOGGER = logging.getLogger("uvicorn.error")
CACHE_FORMAT_VERSION = 2


class EventArchiveStore:
    """Prepares the large archive once, then serves small time windows from daily files."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._data_directory = settings.cache_directory / "prepared"
        self._manifest_path = self._data_directory / "manifest.json"
        self._manifest: dict[str, object] | None = None
        self._wall_started_at: datetime | None = None

    def prepare(self) -> None:
        archive = self._settings.archive_path
        if not archive.is_file():
            raise FileNotFoundError(f"Event archive was not found: {archive}")

        self._settings.cache_directory.mkdir(parents=True, exist_ok=True)
        self._remove_abandoned_preparations()
        fingerprint = self._fingerprint(archive)
        manifest = self._load_manifest()
        if manifest is None or manifest.get("fingerprint") != fingerprint:
            if self._data_directory.exists():
                LOGGER.info("Removing incompatible prepared event cache from %s", self._data_directory)
                shutil.rmtree(self._data_directory)
            LOGGER.info("Preparing event archive %s into %s", archive, self._data_directory)
            self._prepare_archive(archive, fingerprint)
            manifest = self._load_manifest()
        else:
            LOGGER.info("Using prepared event cache from %s", self._data_directory)

        if manifest is None:
            raise RuntimeError("Prepared event manifest is missing")

        self._manifest = manifest
        # The replay begins when the feeder is actually ready, so archive preparation
        # cannot silently consume the first minutes of the configured source range.
        self._wall_started_at = datetime.now(timezone.utc)
        LOGGER.info(
            "Event feed ready: events=%s, cached_source=%s..%s, replay_start=%s, duration=%s",
            manifest["event_count"],
            manifest["source_min_at"],
            manifest["source_max_at"],
            self._settings.source_start_at.isoformat(),
            self._settings.cache_duration,
        )

    def get_events(
        self,
        from_at: datetime,
        to_at: datetime,
        limit: int,
        cursor: str | None,
    ) -> EventPage:
        self._ensure_ready()
        from_utc = _as_utc(from_at)
        to_utc = _as_utc(to_at)
        if from_utc >= to_utc:
            raise ValueError("'from' must be earlier than 'to'")
        if to_utc - from_utc > timedelta(hours=24):
            raise ValueError("A single request window cannot exceed 24 hours")

        offset = self._decode_cursor(cursor, from_utc, to_utc) if cursor else 0
        source_from = self._wall_to_source(from_utc)
        source_to = self._wall_to_source(to_utc)
        events = self._read_source_window(source_from, source_to)
        events.sort(key=lambda event: (event.occurred_at, event.id))

        page_items = events[offset : offset + limit]
        next_offset = offset + len(page_items)
        has_more = next_offset < len(events)
        next_cursor = self._encode_cursor(from_utc, to_utc, next_offset) if has_more else None
        return EventPage(
            **{
                "from": from_utc,
                "to": to_utc,
                "items": page_items,
                "has_more": has_more,
                "next_cursor": next_cursor,
            }
        )

    def get_status(self) -> FeedStatus:
        self._ensure_ready()
        source_min = self._parse_source_datetime(str(self._manifest["source_min_at"]))
        source_max = self._parse_source_datetime(str(self._manifest["source_max_at"]))
        source_end = self._settings.source_start_at + self._settings.cache_duration
        current_source = self._wall_to_source(datetime.now(timezone.utc))
        return FeedStatus(
            state="exhausted" if current_source >= source_end else "running",
            loaded_events=int(self._manifest["event_count"]),
            source_min_at=source_min,
            source_max_at=source_max,
            source_start_at=self._settings.source_start_at,
            source_end_at=source_end,
            current_source_at=current_source,
            wall_started_at=self._wall_started_at,
            exhausted=current_source >= source_end,
        )

    def _read_source_window(self, source_from: datetime, source_to: datetime) -> list[EventDto]:
        source_min = self._parse_source_datetime(str(self._manifest["source_min_at"]))
        source_max = self._parse_source_datetime(str(self._manifest["source_max_at"]))
        if source_to <= source_min or source_from > source_max:
            return []

        result: list[EventDto] = []
        current_day = source_from.date()
        last_day = source_to.date()
        while current_day <= last_day:
            day_path = self._data_directory / "days" / f"{current_day.isoformat()}.csv"
            if day_path.is_file():
                with day_path.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    for row in reader:
                        source_at = self._row_datetime(row)
                        if source_from <= source_at < source_to:
                            result.append(
                                EventDto(
                                    id=int(row["ид_события"]),
                                    channel_id=int(row["ид_канала_данных"]),
                                    occurred_at=self._source_to_wall(source_at),
                                    source_occurred_at=source_at,
                                    is_alarm=row["тревожное"].strip().lower() in TRUE_VALUES,
                                    value=row["значение_датчика"],
                                )
                            )
            current_day += timedelta(days=1)
        return result

    def _prepare_archive(self, archive: Path, fingerprint: str) -> None:
        cache_directory = self._settings.cache_directory
        cache_directory.mkdir(parents=True, exist_ok=True)
        temporary = cache_directory / f"preparing-{uuid.uuid4().hex}"
        days_directory = temporary / "days"
        days_directory.mkdir(parents=True)

        event_count = 0
        scanned_count = 0
        source_min: datetime | None = None
        source_max: datetime | None = None
        archive_min: datetime | None = None
        archive_max: datetime | None = None
        window_start = self._settings.source_start_at
        window_end = window_start + self._settings.cache_duration
        writers: OrderedDict[str, tuple[TextIO, csv.DictWriter]] = OrderedDict()

        try:
            with ExitStack() as stack:
                stream = stack.enter_context(self._open_archive_stream(archive))
                reader = csv.DictReader(stream)
                if reader.fieldnames != EXPECTED_COLUMNS:
                    raise ValueError(
                        f"Unexpected event CSV columns: {reader.fieldnames}; expected: {EXPECTED_COLUMNS}"
                    )

                for row in reader:
                    source_at = self._row_datetime(row)
                    scanned_count += 1
                    archive_min = source_at if archive_min is None else min(archive_min, source_at)
                    archive_max = source_at if archive_max is None else max(archive_max, source_at)
                    if scanned_count % 1_000_000 == 0:
                        LOGGER.info(
                            "Scanned %s rows; cached %s rows from the selected window",
                            f"{scanned_count:,}",
                            f"{event_count:,}",
                        )
                    if not window_start <= source_at < window_end:
                        continue

                    day_key = source_at.date().isoformat()
                    writer = self._get_day_writer(day_key, days_directory, writers)
                    writer.writerow(row)
                    event_count += 1
                    source_min = source_at if source_min is None else min(source_min, source_at)
                    source_max = source_at if source_max is None else max(source_max, source_at)

            for stream, _ in writers.values():
                stream.close()
            writers.clear()

            if event_count == 0 or source_min is None or source_max is None:
                archive_range = (
                    f"{archive_min.isoformat()}..{archive_max.isoformat()}"
                    if archive_min is not None and archive_max is not None
                    else "empty"
                )
                raise ValueError(
                    "The selected feed window contains no events: "
                    f"{window_start.isoformat()}..{window_end.isoformat()}; archive range: {archive_range}"
                )

            manifest = {
                "fingerprint": fingerprint,
                "event_count": event_count,
                "scanned_event_count": scanned_count,
                "source_min_at": source_min.isoformat(),
                "source_max_at": source_max.isoformat(),
                "source_start_at": window_start.isoformat(),
                "source_end_at": window_end.isoformat(),
            }
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            os.replace(temporary, self._data_directory)
            LOGGER.info(
                "Archive scan completed: scanned=%s, cached=%s",
                f"{scanned_count:,}",
                f"{event_count:,}",
            )
        except Exception:
            for stream, _ in writers.values():
                stream.close()
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def _get_day_writer(
        self,
        day_key: str,
        days_directory: Path,
        writers: OrderedDict[str, tuple[TextIO, csv.DictWriter]],
    ) -> csv.DictWriter:
        existing = writers.pop(day_key, None)
        if existing is not None:
            writers[day_key] = existing
            return existing[1]

        if len(writers) >= 16:
            _, (old_stream, _) = writers.popitem(last=False)
            old_stream.close()

        path = days_directory / f"{day_key}.csv"
        is_new = not path.exists()
        stream = path.open("a", encoding="utf-8", newline="")
        writer = csv.DictWriter(stream, fieldnames=EXPECTED_COLUMNS)
        if is_new:
            writer.writeheader()
        writers[day_key] = (stream, writer)
        return writer

    def _open_archive_stream(self, archive: Path) -> TextIO:
        if archive.suffix.lower() == ".csv":
            return archive.open("r", encoding="utf-8-sig", newline="")
        if archive.suffix.lower() != ".7z":
            raise ValueError(f"Unsupported event source format: {archive.suffix}")

        process = subprocess.Popen(
            ["7z", "x", "-so", str(archive)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.stdout is None:
            process.kill()
            raise RuntimeError("Failed to open 7z output stream")
        return _ProcessTextStream(process)

    def _row_datetime(self, row: dict[str, str]) -> datetime:
        value = datetime.fromisoformat(f"{row['дата']}T{row['время']}")
        return value.replace(tzinfo=self._settings.time_zone)

    def _wall_to_source(self, wall_at: datetime) -> datetime:
        return self._settings.source_start_at + (_as_utc(wall_at) - self._wall_started_at)

    def _source_to_wall(self, source_at: datetime) -> datetime:
        return self._wall_started_at + (source_at - self._settings.source_start_at)

    def _parse_source_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(self._settings.time_zone)

    def _load_manifest(self) -> dict[str, object] | None:
        if not self._manifest_path.is_file():
            return None
        return json.loads(self._manifest_path.read_text(encoding="utf-8"))

    def _fingerprint(self, path: Path) -> str:
        stat = path.stat()
        value = ":".join(
            [
                str(CACHE_FORMAT_VERSION),
                path.name,
                str(stat.st_size),
                str(stat.st_mtime_ns),
                self._settings.source_start_at.isoformat(),
                str(self._settings.cache_duration.total_seconds()),
            ]
        ).encode()
        return hashlib.sha256(value).hexdigest()

    def _remove_abandoned_preparations(self) -> None:
        for path in self._settings.cache_directory.glob("preparing-*"):
            if path.is_dir():
                LOGGER.info("Removing abandoned event cache preparation from %s", path)
                shutil.rmtree(path)

    @staticmethod
    def _encode_cursor(from_at: datetime, to_at: datetime, offset: int) -> str:
        payload = json.dumps(
            {"from": from_at.isoformat(), "to": to_at.isoformat(), "offset": offset},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str, from_at: datetime, to_at: datetime) -> int:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            if payload["from"] != from_at.isoformat() or payload["to"] != to_at.isoformat():
                raise ValueError("Cursor does not belong to the requested window")
            offset = int(payload["offset"])
            if offset < 0:
                raise ValueError("Cursor offset cannot be negative")
            return offset
        except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError, base64.binascii.Error) as exc:
            raise ValueError("Invalid cursor") from exc

    def _ensure_ready(self) -> None:
        if self._manifest is None or self._wall_started_at is None:
            raise RuntimeError("Event feed is not ready")


class _ProcessTextStream(io.TextIOBase):
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process
        self._stream = io.TextIOWrapper(process.stdout, encoding="utf-8-sig", newline="")

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> str:
        return self._stream.read(size)

    def readline(self, size: int = -1) -> str:
        return self._stream.readline(size)

    def __iter__(self):
        return iter(self._stream)

    def close(self) -> None:
        if self.closed:
            return
        self._stream.close()
        return_code = self._process.wait()
        stderr = self._process.stderr.read().decode(errors="replace") if self._process.stderr else ""
        if self._process.stderr:
            self._process.stderr.close()
        super().close()
        if return_code != 0:
            raise RuntimeError(f"7z extraction failed with exit code {return_code}: {stderr.strip()}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a UTC offset")
    return value.astimezone(timezone.utc)
