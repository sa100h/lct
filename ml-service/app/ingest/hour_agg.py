"""Stage 1b: per-(channel, day, hour) aggregate of the full SMVU journal.

Companion to aggregate.py. The raw journal has a separate `время` (HH:MM:SS)
column that the day-granular stage ignores. This stage bins events by hour-of-day
so downstream features can model intra-day periodicity (the tracked hour-of-day gap).

The counting and cleaning rules are shared with the day stage and with the
``events_log`` collector (:mod:`app.ingest.reduce`) — this module only adds the
hour dimension.
Outputs: ``<data root>/agg/agg-hour-<year>.parquet`` (root = ``LCT_DATA_DIR``).

Grain is (channel, day, hour) — rows emitted only where events occurred
(a channel reporting the same day is binned into the hours it actually reported,
never zero-filled across 24 hours). hour=-1 marks rows whose `время` was missing.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from app.config import AGG_DIR, EXTRACTED_DIR
from app.ingest.reduce import (
    CHUNK,
    HOUR_KEYS,
    channel_ref,
    finalize,
    per_row_counts,
    reduce_parts,
)

EX = EXTRACTED_DIR
AGG = AGG_DIR

COLS = ["ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"]


def hour_agg_year(year: int) -> None:
    f = EX / str(year) / f"ext-journal-{year}.csv"
    t0 = time.time()
    parts: list[pd.DataFrame | None] = []
    n_raw = 0
    n_invalid = 0
    n_bad_hour = 0
    dtype_map = channel_ref()["тип_датчика"]  # channel -> sensor type
    for chunk in pd.read_csv(f, usecols=COLS, dtype=str, chunksize=CHUNK, low_memory=False):
        partial, stats = per_row_counts(chunk, dtype_map, hour=True, fault1970=False)
        n_raw += stats["raw"]
        n_invalid += stats["invalid"]
        n_bad_hour += stats["bad_hour"]
        if partial is not None:
            parts.append(partial)

    agg = finalize(
        reduce_parts(parts, HOUR_KEYS, fault1970=False),
        year,
        HOUR_KEYS,
        fault1970=False,
        what="channel-day-hours",
    )
    AGG.mkdir(parents=True, exist_ok=True)
    out = AGG / f"agg-hour-{year}.parquet"
    agg.to_parquet(out, index=False)
    print(f"{year}: raw={n_raw:,} invalid_dropped={n_invalid:,} bad_hour={n_bad_hour:,} "
          f"hour_agg_rows={len(agg):,} -> {out.stat().st_size/1e6:.1f}MB  ({time.time()-t0:.0f}s)",
          flush=True)


def main() -> None:
    years = [int(y) for y in sorted(p.name for p in EX.iterdir() if p.is_dir() and p.name.isdigit())]
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    for y in years:
        hour_agg_year(y)
    print("HOUR AGG ALL DONE", flush=True)


if __name__ == "__main__":
    main()
