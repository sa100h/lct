"""Emit a repeatable, test-only SQL seed for the app-service event references.

Usage (from the repository root):
    python scripts/seed_event_feed_references.py --apply

Without --apply, writes SQL to standard output for review. With --apply,
sends UTF-8 bytes directly to psql inside the running Compose postgres service.

The SQL uses the organizer's CSV files in ml-data and runs in one transaction.
No database driver is required on the host. Existing rows are never overwritten.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_CSV = REPO_ROOT / "ml-data" / "справочник_каналов_датчиков.csv"
OBJECTS_CSV = REPO_ROOT / "ml-data" / "справочник_объектов_диспетчер.csv"
MISSING_PARENT_ID = 3831
UNKNOWN_STATUS_ID = 0
BATCH_SIZE = 500


def read_csv(path: Path, expected_columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise ValueError(f"Unexpected columns in {path}: {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty reference file: {path}")
    return rows


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_int(value: str, label: str) -> int:
    number = int(value)
    if not 0 <= number <= 2_147_483_647:
        raise ValueError(f"{label} is outside PostgreSQL integer range: {value}")
    return number


def require_unique(values: list[int] | list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label} in source data")


def insert_rows(table: str, columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        values = ",\n    ".join("(" + ", ".join(row) + ")" for row in batch)
        print(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n"
            f"    {values}\nON CONFLICT (id) DO NOTHING;"
        )


def ordered_objects(objects: dict[int, dict[str, str]]) -> list[tuple[int, dict[str, str]]]:
    ordered: list[tuple[int, dict[str, str]]] = []
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(object_id: int) -> None:
        if object_id in visited:
            return
        if object_id in visiting:
            raise ValueError(f"Cycle in dispatcher object hierarchy at {object_id}")
        visiting.add(object_id)
        row = objects[object_id]
        parent = row["родитель"].strip()
        if parent:
            parent_id = sql_int(parent, "parent ID")
            if parent_id not in objects:
                raise ValueError(f"Missing parent {parent_id} for object {object_id}")
            visit(parent_id)
        visiting.remove(object_id)
        visited.add(object_id)
        ordered.append((object_id, row))

    for object_id in sorted(objects):
        visit(object_id)
    return ordered


def main() -> None:
    channels = read_csv(
        CHANNELS_CSV,
        (
            "ид_канала_данных",
            "тип_инж_системы",
            "тип_датчика",
            "тег_инженерной_системы",
            "название_датчика",
            "ид_объект",
        ),
    )
    object_rows = read_csv(
        OBJECTS_CSV,
        (
            "ид_объект",
            "иерархия_уровень",
            "родитель",
            "вид_объекта",
            "диспетчерское_название_объекта",
        ),
    )

    channel_ids = [sql_int(row["ид_канала_данных"], "channel ID") for row in channels]
    object_ids = [sql_int(row["ид_объект"], "object ID") for row in object_rows]
    require_unique(channel_ids, "channel IDs")
    require_unique(object_ids, "object IDs")
    objects = dict(zip(object_ids, object_rows, strict=True))

    missing_parents = {
        sql_int(row["родитель"], "parent ID")
        for row in object_rows
        if row["родитель"].strip()
        and sql_int(row["родитель"], "parent ID") not in objects
    }
    if missing_parents != {MISSING_PARENT_ID}:
        raise ValueError(f"Unexpected missing object parents: {sorted(missing_parents)}")
    if MISSING_PARENT_ID in objects:
        raise ValueError(f"Placeholder parent ID {MISSING_PARENT_ID} is already in source data")
    objects[MISSING_PARENT_ID] = {
        "ид_объект": str(MISSING_PARENT_ID),
        "иерархия_уровень": "0",
        "родитель": "",
        "вид_объекта": "district",
        "диспетчерское_название_объекта": "Тестовый объект без исходной записи",
    }

    for row in channels:
        object_id = sql_int(row["ид_объект"], "channel object ID")
        if object_id not in objects:
            raise ValueError(f"Channel references unknown object {object_id}")
        if not row["название_датчика"].strip():
            raise ValueError(f"Channel {row['ид_канала_данных']} has no name")

    systems = sorted({row["тип_инж_системы"].strip() for row in channels})
    sensor_type_system = {
        row["тип_датчика"].strip(): row["тип_инж_системы"].strip()
        for row in channels
    }
    if not all(systems) or not all(sensor_type_system):
        raise ValueError("Empty system or sensor type name")
    for row in channels:
        sensor_type = row["тип_датчика"].strip()
        system = row["тип_инж_системы"].strip()
        if sensor_type_system[sensor_type] != system:
            raise ValueError(f"Sensor type {sensor_type} belongs to multiple systems")

    object_types = sorted({row["вид_объекта"].strip() for row in objects.values()})
    if not all(object_types):
        raise ValueError("Empty object type name")
    system_ids = {name: index for index, name in enumerate(systems, start=1)}
    sensor_type_ids = {
        name: index for index, name in enumerate(sorted(sensor_type_system), start=1)
    }
    object_type_ids = {name: index for index, name in enumerate(object_types, start=1)}

    print("BEGIN;")
    insert_rows(
        "engineering_systems",
        ("id", "name"),
        [(str(system_ids[name]), sql_text(name)) for name in systems],
    )
    insert_rows(
        "sensor_types",
        ("id", "name", "engineering_system_id"),
        [
            (
                str(sensor_type_ids[name]),
                sql_text(name),
                str(system_ids[sensor_type_system[name]]),
            )
            for name in sorted(sensor_type_system)
        ],
    )
    insert_rows(
        "object_types",
        ("id", "name"),
        [(str(object_type_ids[name]), sql_text(name)) for name in object_types],
    )
    for object_id, row in ordered_objects(objects):
        parent = row["родитель"].strip()
        insert_rows(
            "dispatcher_objects",
            (
                "id", "hierarchy_level", "parent_id", "object_type_id",
                "dispatcher_object_name", "coordinates",
            ),
            [
                (
                    str(object_id),
                    str(sql_int(row["иерархия_уровень"], "hierarchy level")),
                    str(sql_int(parent, "parent ID")) if parent else "NULL",
                    str(object_type_ids[row["вид_объекта"].strip()]),
                    sql_text(f"{row['диспетчерское_название_объекта'].strip()} [id:{object_id}]"),
                    "0.0",
                )
            ],
        )
    insert_rows(
        "sensor_statuses",
        ("id", "name"),
        [(str(UNKNOWN_STATUS_ID), sql_text("Неизвестно (тест)"))],
    )
    insert_rows(
        "sensor_channels",
        ("id", "sensor_type_id", "sensor_name", "dispatcher_object_id", "sensor_status_id"),
        [
            (
                str(channel_id),
                str(sensor_type_ids[row["тип_датчика"].strip()]),
                sql_text(f"{row['название_датчика'].strip()} [id:{channel_id}]"),
                str(sql_int(row["ид_объект"], "channel object ID")),
                str(UNKNOWN_STATUS_ID),
            )
            for channel_id, row in zip(channel_ids, channels, strict=True)
        ],
    )
    print("COMMIT;")
    print(
        "SELECT 'sensor_channels' AS table_name, count(*) AS rows FROM sensor_channels "
        "UNION ALL SELECT 'dispatcher_objects', count(*) FROM dispatcher_objects "
        "UNION ALL SELECT 'sensor_statuses', count(*) FROM sensor_statuses;"
    )
    print(
        f"Prepared test reference seed: {len(systems)} systems, "
        f"{len(sensor_type_ids)} sensor types, {len(object_types)} object types, "
        f"{len(objects)} objects, {len(channels)} channels",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--apply"]:
            sql_output = io.StringIO()
            with redirect_stdout(sql_output):
                main()
            subprocess.run(
                [
                    "docker", "compose", "exec", "-T", "postgres", "psql",
                    "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "app_db", "-q",
                ],
                input=sql_output.getvalue().encode("utf-8"),
                cwd=REPO_ROOT,
                check=True,
            )
        elif not sys.argv[1:]:
            main()
        else:
            raise ValueError("Usage: seed_event_feed_references.py [--apply]")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Reference seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
