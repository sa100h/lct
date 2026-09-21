"""Load confirmed equipment <-> channel pairs into equipment_channel_map.

By decision (2026-09-21) equipment.external_id IS the channel id, so the
mapping is a 1:1 identity; this script records the confirmed pairs so the
app can join equipment to ML predictions through an explicit, verifiable
table instead of an implicit assumption.

Input CSV columns:  equipment_external_id, channel_id, note
   note is optional. channel_id must exist in channel_directory
   (run scripts/load_channel_directory.py first).

Usage:  python scripts/map_equipment_channels.py pairs.csv
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

UPSERT = """
INSERT INTO equipment_channel_map (equipment_external_id, channel_id, note)
VALUES ($1, $2, $3)
ON CONFLICT (equipment_external_id, channel_id) DO UPDATE SET
    note = EXCLUDED.note,
    mapped_at = now()
"""


def read_pairs(csv_path: Path) -> list[tuple]:
    pairs: list[tuple] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader)  # header
        for r in reader:
            if not r or not r[0].strip():
                continue
            r = [c.strip() for c in r] + [""] * (3 - len(r))
            pairs.append((r[0], r[1], r[2] or None))
    return pairs


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
        print(f"pairs csv not found: {csv_path}", file=sys.stderr)
        return 2
    pairs = read_pairs(csv_path)
    if not pairs:
        print("no pairs in csv", file=sys.stderr)
        return 2

    pool = await asyncpg.create_pool(min_size=1, max_size=2,
                                     **_pool_kwargs(os.environ.get("DB_DSN") or DEFAULT_DSN))
    try:
        async with pool.acquire() as conn:
            known = {row[0] for row in await conn.fetch(
                "SELECT channel_id FROM channel_directory")}
            if not known:
                print("channel_directory is empty — run scripts/load_channel_directory.py first",
                      file=sys.stderr)
                return 2

            unknown = sorted({p[1] for p in pairs} - known)
            if unknown:
                print(f"error: {len(unknown)} channel_id(s) not in channel_directory: {unknown[:5]}",
                      file=sys.stderr)
                return 1

            # 1:1 check: one equipment id may only map to one channel (identity mapping).
            from collections import defaultdict
            by_ext: dict[str, set[str]] = defaultdict(set)
            for e, c, _ in pairs:
                by_ext[e].add(c)
            fans = sorted(e for e, chans in by_ext.items() if len(chans) > 1)

            await conn.executemany(UPSERT, pairs)
            total = await conn.fetchval("SELECT count(*) FROM equipment_channel_map")
    finally:
        await pool.close()

    print(f"equipment_channel_map: {len(pairs)} pairs upserted, table now has {total} mappings")
    for e in fans:
        print(f"warning: external_id {e} maps to more than one channel — expected 1:1", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(Path(sys.argv[1]))))
