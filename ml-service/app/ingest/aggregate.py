"""Stage 1: per-(channel, day) aggregate of the full SMVU journal.

Reads extracted per-year journals (19GB total) in 2M-row chunks, pre-reduces
each chunk to (channel, day) partials, then a final groupby per year.
Output: /home/junai/lct/ml-data/agg/agg-<year>.parquet  (int32 counts, float32 stats)

Columns: channel(str), day(yyyy-mm-dd), cabinet(category), ид_объект(category),
n_events, n_alarm, s_<idx> per tracked state (see STATES), n_num, num_sum,
num_sumsq, num_min, num_max.

Cleanliness rules (REPORT.md §7):
  - inline header rows and unknown boolean tokens are dropped;
  - numeric coding artifacts are excluded from num_* stats but NOT from
    n_events/n_alarm/state counts: gas (327.68 / negatives / >100 ppm) and
    thermal (-100..300 degC range);
  - cabinet/object joined from the channel reference (NaN for out-of-ref).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

EX = Path("/home/junai/lct/ml-data/extracted")
AGG = Path("/home/junai/lct/ml-data/agg")
AGG.mkdir(parents=True, exist_ok=True)
REF = Path("/home/junai/lct/ml-data") / "справочник_каналов_датчиков.csv"


def load_channel_ref() -> pd.DataFrame:
    """channel -> (тип_датчика, cabinet, object). cabinet = first digit segment of the tag."""
    ref = pd.read_csv(REF, dtype=str)
    ref["cabinet"] = ref["тег_инженерной_системы"].astype(str).str.extract(r"^(\d+)-")[0]
    ref["cabinet"] = ref["cabinet"].astype("category")
    ref["ид_объект"] = ref["ид_объект"].astype("category")
    return ref.set_index("ид_канала_данных")[["тип_датчика", "cabinet", "ид_объект"]]


CHAN_REF = load_channel_ref()

# Fixed tracked-state set (union across all 4 task categories, from vocab.json).
# Index -> state. Keeping a single shared set keeps agg year tables small.
STATES = [
    "Норма",                       # 0
    "Неопределен",                 # 1
    "Не замкнут",                  # 2
    "Неисправен",                  # 3
    "Обесточен",                   # 4
    "Затоплен",                    # 5
    "Отключено устройство",        # 6
    "Много неисправных устройств", # 7
    "Питание от батарей",          # 8
    "Движения нет",                # 9
    "Обнаружено движение",         # 10
    "Обнаружен дым",               # 11
    "Обнаружен газ",               # 12
    "Внимание",                    # 13
    "Опасность",                   # 14
    "Высокая температура",         # 15
    "Низкая температура",          # 16
    "Замыкание",                   # 17
    "Выключен",                    # 18
    "Включен",                     # 19
    "На охране",                   # 20
    "Снято с охраны",              # 21
    "Обрыв",                       # 22
    "Есть питание",                # 23
    "Питание от сети",             # 24
    "Работают все насосы в АНС",   # 25
]
N_STATES = len(STATES)
STATE_CODE = {s: i for i, s in enumerate(STATES)}

COLS = ["ид_канала_данных", "дата", "тревожное", "значение_датчика"]
CHUNK = 2_000_000
TRUE_TOKENS = {"t", "true", "1", "yes"}
# REPORT.md: cabinet 847 (smoke detectors, line 1.1.58) had a ~45-day line
# artifact 01.05-30.06.2021 («Норма+Неисправен» 1:1 bursts). Drop those
# channel-days instead of letting them inflate 2021 positives.
EXCLUDE_SPANS = [
    # (cabinet, day_start, day_end, years)
    ("847", "2021-05-01", "2021-06-30", {2021}),
]

# Invalid-reading masks per sensor type (REPORT.md §7): gas codes 327.68 /
# negatives (2020-21); thermal codes -3276 / 957-999. Physically gas is
# 0..~50 ppm, temperature is -100..+300 degC.
GAS_TYPES = {"Газовый датчик"}
TEMP_TYPES = {"Тепловой датчик", "Датчик температуры"}


def invalid_mask(dtype: pd.Series, num: pd.Series) -> pd.Series:
    """True where the numeric reading is a coding artifact, not a value."""
    m = num.notna()
    gas = m & dtype.isin(GAS_TYPES) & ((num < 0) | (num > 100))
    temp = m & dtype.isin(TEMP_TYPES) & ((num < -100) | (num > 300))
    return gas | temp


def agg_year(year: int) -> None:
    f = EX / str(year) / f"ext-journal-{year}.csv"
    t0 = time.time()
    parts: list[pd.DataFrame] = []
    n_raw = 0
    n_invalid = 0
    dtype_map = CHAN_REF["тип_датчика"]  # channel -> sensor type
    for chunk in pd.read_csv(f, usecols=COLS, dtype=str, chunksize=CHUNK, low_memory=False):
        n_raw += len(chunk)
        # normalize + drop garbage rows (e.g. inline header row in 2025 file)
        tr = chunk["тревожное"].str.strip().str.lower()
        chunk = chunk[tr.isin(TRUE_TOKENS) | tr.isin({"f", "false", "0", "no"})]
        if chunk.empty:
            continue
        chunk = chunk[chunk["ид_канала_данных"].notna()]
        chan = chunk["ид_канала_данных"].astype(str)
        day = chunk["дата"]
        val = chunk["значение_датчика"].fillna("")
        alarm = tr.loc[chunk.index].isin(TRUE_TOKENS).astype(np.int32)
        num = pd.to_numeric(val, errors="coerce")

        # drop coding artifacts from numeric stats (REPORT.md §7): gas 327.68 /
        # negatives, thermal -3276 / 957..999 — they poison means and spreads
        dt = chan.map(dtype_map)
        inv = invalid_mask(dt, num)
        if inv.any():
            num[inv] = np.nan
            n_invalid += int(inv.sum())

        g = pd.DataFrame(
            {
                "channel": chan.to_numpy(),
                "day": day.to_numpy(),
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

        # pre-reduce within chunk: same day may be split across chunks -> final groupby later
        red = g.groupby(["channel", "day"], sort=False).agg(
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

    # concat all partials (bounded: a few 100k-row frames per year) then final groupby
    df = pd.concat(parts, ignore_index=True)
    agg = df.groupby(["channel", "day"], sort=False).agg(
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
    for c in ["n_events", "n_alarm", "n_num"] + [f"s_{i}" for i in range(N_STATES)]:
        agg[c] = agg[c].astype(np.int32)
    for c in ["num_sum", "num_sumsq", "num_min", "num_max"]:
        agg[c] = agg[c].astype(np.float32)
    # cabinet/object per channel (unmatched = 1142 out-of-reference channels -> NaN)
    agg = agg.join(CHAN_REF[["cabinet", "ид_объект"]], on="channel", how="left")
    agg["cabinet"] = agg["cabinet"].astype("category")
    agg["ид_объект"] = agg["ид_объект"].astype("category")
    # artifact isolation: drop (cabinet, day-span, year) regions that REPORT.md
    # identifies as system noise, not real incidents
    for cab, d0, d1, yset in EXCLUDE_SPANS:
        if year in yset:
            mask = (agg["cabinet"] == cab) & agg["day"].between(d0, d1)
            if mask.any():
                n_drop = int(mask.sum())
                agg = agg[~mask].copy()
                print(f"  [exclude] {cab} {d0}..{d1} year={year}: dropped {n_drop:,} channel-days", flush=True)
    out = AGG / f"agg-{year}.parquet"
    agg.to_parquet(out, index=False)
    print(f"{year}: raw={n_raw:,} invalid_dropped={n_invalid:,} agg_rows={len(agg):,} -> {out.stat().st_size/1e6:.1f}MB  ({time.time()-t0:.0f}s)", flush=True)


def parts_total(frames: list[pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat(frames, ignore_index=True)
    return df.groupby(["channel", "day"], sort=False).agg(
        n_events=("n_events", "sum"),
        n_alarm=("n_alarm", "sum"),
        n_num=("n_num", "sum"),
        num_sum=("num_sum", "sum"),
        num_sumsq=("num_sumsq", "sum"),
        num_min=("num_min", "min"),
        num_max=("num_max", "max"),
        **{f"s_{i}": (f"s_{i}", "sum") for i in range(N_STATES)},
    ).reset_index()


def main() -> None:
    years = [int(y) for y in sorted(p.name for p in EX.iterdir() if p.is_dir() and p.name.isdigit())]
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    for y in years:
        agg_year(y)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
