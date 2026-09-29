"""Stage 1: per-(channel, day) aggregate of the full SMVU journal.

Reads extracted per-year journals (19GB total) in 2M-row chunks, pre-reduces
each chunk to (channel, day) partials, then a final groupby per year.
Output: ``<data root>/agg/agg-<year>.parquet`` (int32 counts, float32 stats);
the root is ``LCT_DATA_DIR`` (see :mod:`app.config`).

Columns: channel(str), day(yyyy-mm-dd), cabinet(category), ид_объект(category),
n_events, n_alarm, s_<idx> per tracked state (see STATES), n_num, num_sum,
num_sumsq, num_min, num_max.

Cleanliness rules (REPORT.md §7):
  - inline header rows and unknown boolean tokens are dropped;
  - numeric coding artifacts are excluded from num_* stats but NOT from
    n_events/n_alarm/state counts: gas (327.68 / negatives / >100 ppm) and
    thermal (-100..300 degC range);
  - cabinet/object joined from the channel reference (NaN for out-of-ref).
Organizer answers (2026-09-24, справочник_состояний.csv + Q&A):
  - 01.01.1970 03:00:0x value artifacts = date fault -> counted in n_fault1970
    (new column) and never treated as binary 0/1;
  - gas numeric = %volume methane, alarm threshold 1%, 5-15% = ignition band;
    values outside the physical band -> fault, already excluded from num_*
    via invalid_mask.

The classification rules live in :mod:`app.ingest.reduce`, shared with the
``events_log`` collector (ml-data-prep) so both sources emit identical rows.
This module only drives them over the CSV journal, and re-exports the constants
that the other stages import from here.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from app.config import AGG_DIR, EXTRACTED_DIR
from app.ingest.reduce import (
    CHUNK,
    DAY_KEYS,
    EXCLUDE_SPANS,
    GAS_TYPES,
    N_STATES,
    STATE_CODE,
    STATES,
    TEMP_TYPES,
    TRUE_TOKENS,
    channel_ref,
    finalize,
    per_row_counts,
    reduce_parts,
)

EX = EXTRACTED_DIR
AGG = AGG_DIR

COLS = ["ид_канала_данных", "дата", "тревожное", "значение_датчика"]


def __getattr__(name: str):
    """Back-compat (PEP 562): names that used to be defined in this module.

    ``CHAN_REF``, ``load_channel_ref`` and ``invalid_mask`` now live in
    :mod:`app.ingest.reduce`; scripts that imported them from here keep working.
    """
    from app.ingest import reduce as _reduce

    if name == "CHAN_REF":
        return _reduce.channel_ref()
    if name in {"load_channel_ref", "invalid_mask"}:
        return getattr(_reduce, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def agg_year(year: int) -> None:
    f = EX / str(year) / f"ext-journal-{year}.csv"
    t0 = time.time()
    parts: list[pd.DataFrame | None] = []
    n_raw = 0
    n_invalid = 0
    dtype_map = channel_ref()["тип_датчика"]  # channel -> sensor type
    for chunk in pd.read_csv(f, usecols=COLS, dtype=str, chunksize=CHUNK, low_memory=False):
        partial, stats = per_row_counts(chunk, dtype_map)
        n_raw += stats["raw"]
        n_invalid += stats["invalid"]
        if partial is not None:
            parts.append(partial)

    agg = finalize(reduce_parts(parts, DAY_KEYS), year, DAY_KEYS)
    AGG.mkdir(parents=True, exist_ok=True)
    out = AGG / f"agg-{year}.parquet"
    agg.to_parquet(out, index=False)
    print(f"{year}: raw={n_raw:,} invalid_dropped={n_invalid:,} agg_rows={len(agg):,} -> "
          f"{out.stat().st_size/1e6:.1f}MB  ({time.time()-t0:.0f}s)", flush=True)


def main() -> None:
    years = [int(y) for y in sorted(p.name for p in EX.iterdir() if p.is_dir() and p.name.isdigit())]
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    for y in years:
        agg_year(y)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
