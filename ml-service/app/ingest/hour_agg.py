"""Stage 1b: per-(channel, day, hour) aggregate of the full SMVU journal.

Companion to aggregate.py. The raw journal has a separate `время` (HH:MM:SS)
column that the day-granular stage ignores. This stage bins events by hour-of-day
so downstream features can model intra-day periodicity (the tracked hour-of-day gap).

Same OOM-safe streaming pattern as aggregate.py: read 2M-row chunks, pre-reduce
each to (channel, day, hour) partials, concat, final groupby per year.
Outputs: /home/junai/lct/ml-data/agg/agg-hour-<year>.parquet

Grain is (channel, day, hour) — rows emitted only where events occurred
(a channel reporting the same day is binned into the hours it actually reported,
never zero-filled across 24 hours). hour=-1 marks rows whose `время` was missing.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.ingest.aggregate import (
    AGG,
    CHAN_REF,
    CHUNK,
    EX,
    EXCLUDE_SPANS,
    GAS_TYPES,
    N_STATES,
    STATES,
    TEMP_TYPES,
    load_channel_ref,
)

COLS = ["ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"]
TRUE_TOKENS = {"t", "true", "1", "yes"}


def _invalid_mask(dtype: pd.Series, num: pd.Series) -> pd.Series:
    """True where the numeric reading is a coding artifact (mirrors aggregate.py)."""
    m = num.notna()
    gas = m & dtype.isin(GAS_TYPES) & ((num < 0) | (num > 100))
    temp = m & dtype.isin(TEMP_TYPES) & ((num < -100) | (num > 300))
    return gas | temp


def hour_agg_year(year: int) -> None:
    f = EX / str(year) / f"ext-journal-{year}.csv"
    t0 = time.time()
    parts: list[pd.DataFrame] = []
    n_raw = 0
    n_invalid = 0
    n_bad_hour = 0
    dtype_map = CHAN_REF["тип_датчика"]  # channel -> sensor type
    for chunk in pd.read_csv(f, usecols=COLS, dtype=str, chunksize=CHUNK, low_memory=False):
        n_raw += len(chunk)
        tr = chunk["тревожное"].str.strip().str.lower()
        chunk = chunk[tr.isin(TRUE_TOKENS) | tr.isin({"f", "false", "0", "no"})]
        if chunk.empty:
            continue
        chunk = chunk[chunk["ид_канала_данных"].notna()]
        chan = chunk["ид_канала_данных"].astype(str)
        day = chunk["дата"].fillna("")
        val = chunk["значение_датчика"].fillna("")
        alarm = tr.loc[chunk.index].isin(TRUE_TOKENS).astype(np.int32)
        num = pd.to_numeric(val, errors="coerce")

        # hour-of-day from the separate `время` column (HH:MM:SS)
        hour = pd.to_numeric(chunk["время"].fillna("").str[:2].str.strip(), errors="coerce")
        n_bad_hour += int(hour.isna().sum())
        hour = hour.fillna(-1).astype(np.int32)

        dt = chan.map(dtype_map)
        inv = _invalid_mask(dt, num)
        if inv.any():
            num[inv] = np.nan
            n_invalid += int(inv.sum())

        g = pd.DataFrame(
            {
                "channel": chan.to_numpy(),
                "day": day.to_numpy(),
                "hour": hour.to_numpy(),
                "n_events": np.ones(len(chunk), np.int32),
                "n_alarm": alarm.to_numpy(),
                "n_num": num.notna().to_numpy(np.int32),
                "num_sum": num.fillna(0.0).to_numpy(np.float32),
                "num_sumsq": (num ** 2).fillna(0.0).to_numpy(np.float32),
                "num_min": num.to_numpy(np.float32),
                "num_max": num.to_numpy(np.float32),
            }
        )
        for i in range(N_STATES):
            g[f"s_{i}"] = (val.to_numpy() == STATES[i]).astype(np.int8)

        red = g.groupby(["channel", "day", "hour"], sort=False).agg(
            n_events=("n_events", "sum"),
            n_alarm=("n_alarm", "sum"),
            n_num=("n_num", "sum"),
            num_sum=("num_sum", "sum"),
            num_sumsq=("num_sumsq", "sum"),
            num_min=("num_min", "min"),
            num_max=("num_max", "max"),
            **{f"s_{i}": (f"s_{i}", "sum") for i in range(N_STATES)},
        ).reset_index()
        parts.append(red)

    df = pd.concat(parts, ignore_index=True)
    agg = df.groupby(["channel", "day", "hour"], sort=False).agg(
        n_events=("n_events", "sum"),
        n_alarm=("n_alarm", "sum"),
        n_num=("n_num", "sum"),
        num_sum=("num_sum", "sum"),
        num_sumsq=("num_sumsq", "sum"),
        num_min=("num_min", "min"),
        num_max=("num_max", "max"),
        **{f"s_{i}": (f"s_{i}", "sum") for i in range(N_STATES)},
    ).reset_index()
    agg["channel"] = agg["channel"].astype(str)
    agg["day"] = agg["day"].astype(str)
    agg["hour"] = agg["hour"].astype(np.int32)
    for c in ["n_events", "n_alarm", "n_num"] + [f"s_{i}" for i in range(N_STATES)]:
        agg[c] = agg[c].astype(np.int32)
    for c in ["num_sum", "num_sumsq", "num_min", "num_max"]:
        agg[c] = agg[c].astype(np.float32)

    # cabinet/object join + identical artifact exclusion as the day stage
    agg = agg.join(CHAN_REF[["cabinet", "ид_объект"]], on="channel", how="left")
    agg["cabinet"] = agg["cabinet"].astype("category")
    agg["ид_объект"] = agg["ид_объект"].astype("category")
    for cab, d0, d1, yset in EXCLUDE_SPANS:
        if year in yset:
            mask = (agg["cabinet"] == cab) & agg["day"].between(d0, d1)
            if mask.any():
                n_drop = int(mask.sum())
                agg = agg[~mask].copy()
                print(f"  [exclude] {cab} {d0}..{d1} year={year}: dropped {n_drop:,} channel-day-hours", flush=True)

    out = AGG / f"agg-hour-{year}.parquet"
    agg.to_parquet(out, index=False)
    print(f"{year}: raw={n_raw:,} invalid_dropped={n_invalid:,} bad_hour={n_bad_hour:,} "
          f"hour_agg_rows={len(agg):,} -> {out.stat().st_size/1e6:.1f}MB  ({time.time()-t0:.0f}s)", flush=True)


def main() -> None:
    years = [int(y) for y in sorted(p.name for p in EX.iterdir() if p.is_dir() and p.name.isdigit())]
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    for y in years:
        hour_agg_year(y)
    print("HOUR AGG ALL DONE", flush=True)


if __name__ == "__main__":
    main()
