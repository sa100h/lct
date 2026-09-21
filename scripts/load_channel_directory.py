"""Load the organizer's channel reference into channel_directory.

Reads ml-data/справочник_каналов_датчиков_NEW.csv (columns:
ид_канала_данных, тип_инж_системы, тип_датчика, тег_инженерной_системы,
название_датчика, ид_объект) and upserts every row. Idempotent: safe to
re-run after the register is updated.

Usage:  python scripts/load_channel_directory.py [path-to-csv]
Env:    DB_DSN (default: local dev app_db)
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg

DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=app_db user=app_service password=app_dev"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "ml-data" / "справочник_каналов_датчиков_NEW.csv"

UPSERT = """
INSERT INTO channel_directory
    (channel_id, type_system, type_sensor, tag_cabinet, sensor_name, object_id)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (channel_id) DO UPDATE SET
    type_system  = EXCLUDED.type_system,
    type_sensor  = EXCLUDED.type_sensor,
    tag_cabinet  = EXCLUDED.tag_cabinet,
    sensor_name  = EXCLUDED.sensor_name,
    object_id    = EXCLUDED.object_id,
    loaded_at    = now()
"""


def read_rows(csv_path: Path) -> list[tuple]:
    rows: list[tuple] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader)  # header
        for r in reader:
            if not r or not r[0].strip():
                continue
            # Pad/trim to 6 columns defensively.
            r = [c.strip() for c in r[:6]] + [""] * (6 - min(len(r), 6))
            rows.append(tuple(r))
    return rows


def _pool_kwargs(dsn: str) -> dict:
    """Accept both URI (postgres://...) and key=value DSNs (asyncpg kwargs)."""
    if dsn.startswith(("postgres://", "postgresql://")):
        return {"dsn": dsn}
    rename = {"dbname": "database"}
    return {rename.get(k, k): v
            for kv in dsn.split() if "=" in kv
            for k, v in [kv.split("=", 1)]}


async def main(csv_path: Path) -> int:
    if not csv_path.exists():
        print(f"csv not found: {csv_path}", file=sys.stderr)
        return 2
    rows = read_rows(csv_path)
    bad = [r for r in rows if not r[0].isdigit()]
    if bad:
        print(f"warning: {len(bad)} rows with non-numeric channel_id, e.g. {bad[:3]}", file=sys.stderr)

    pool = await asyncpg.create_pool(min_size=1, max_size=2,
                                     **_pool_kwargs(os.environ.get("DB_DSN") or DEFAULT_DSN))
    try:
        async with pool.acquire() as conn:
            await conn.executemany(UPSERT, rows)
            total = await conn.fetchval("SELECT count(*) FROM channel_directory")
            objects = await conn.fetchval("SELECT count(DISTINCT object_id) FROM channel_directory")
    finally:
        await pool.close()
    print(f"channel_directory: {len(rows)} rows upserted ({len(bad)} non-numeric), "
          f"table now has {total} channels across {objects} objects")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    sys.exit(asyncio.run(main(path)))
