"""Shared reduction of journal-style event rows into channel-day aggregates.

Why this module exists
----------------------
Two sources feed the training aggregates: the organizer's extracted journal
(``aggregate.py`` / ``hour_agg.py``, CSV files) and the live ``events_log``
table (the nightly refresh in ``ml-data-prep``). Both MUST classify a reading
identically — alarm token, numeric value vs state name, ``01.01.1970``
timestamp artifacts, out-of-band gas/thermal codes — or freshly collected days
would not look like the history they get appended to.

So the rules live here once:

``per_row_counts(rows, dtype_map, ...)``
    normalize one chunk/frame, drop garbage rows, count events/alarms/states
    and numeric stats, then pre-reduce to the grain (keeps memory bounded).
``reduce_parts(parts, keys, ...)``
    concat the per-chunk partials and aggregate again (a day may be split
    across chunks).
``finalize(agg, year, keys, ...)``
    dtypes, cabinet/object from the channel reference, artifact spans dropped.

Input contract: the journal's own column names (``ид_канала_данных``, ``дата``,
``тревожное``, ``значение_датчика``, ``время``); a DB collector renames to
these. Grains: ``DAY_KEYS`` = (channel, day), ``HOUR_KEYS`` = (channel, day, hour).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.config import DATA_DIR

CHUNK = 2_000_000

REF = DATA_DIR / "справочник_каналов_датчиков.csv"

DAY_KEYS: tuple[str, ...] = ("channel", "day")
HOUR_KEYS: tuple[str, ...] = ("channel", "day", "hour")

TRUE_TOKENS = {"t", "true", "1", "yes"}
FALSE_TOKENS = {"f", "false", "0", "no"}

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

_STATE_COLS = [f"s_{i}" for i in range(N_STATES)]
_INT_COLS = ["n_events", "n_alarm", "n_num"]
_FLOAT_COLS = ["num_sum", "num_sumsq", "num_min", "num_max"]

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


def load_channel_ref() -> pd.DataFrame:
    """channel -> (тип_датчика, cabinet, object). cabinet = first digit segment of the tag."""
    ref = pd.read_csv(REF, dtype=str)
    ref["cabinet"] = ref["тег_инженерной_системы"].astype(str).str.extract(r"^(\d+)-")[0]
    ref["cabinet"] = ref["cabinet"].astype("category")
    ref["ид_объект"] = ref["ид_объект"].astype("category")
    return ref.set_index("ид_канала_данных")[["тип_датчика", "cabinet", "ид_объект"]]


_CHAN_REF: pd.DataFrame | None = None


def channel_ref() -> pd.DataFrame:
    """channel -> (тип_датчика, cabinet, object), loaded on first use.

    Lazy on purpose: importing this module must not touch the data tree, so it
    stays importable on a box (or CI runner) without ``ml-data``.
    """
    global _CHAN_REF
    if _CHAN_REF is None:
        _CHAN_REF = load_channel_ref()
    return _CHAN_REF


def __getattr__(name: str):
    """Keep ``CHAN_REF`` working as a module attribute (PEP 562)."""
    if name == "CHAN_REF":
        return channel_ref()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def invalid_mask(dtype: pd.Series, num: pd.Series) -> pd.Series:
    """True where the numeric reading is a coding artifact, not a value."""
    m = num.notna()
    gas = m & dtype.isin(GAS_TYPES) & ((num < 0) | (num > 100))
    temp = m & dtype.isin(TEMP_TYPES) & ((num < -100) | (num > 300))
    return gas | temp


def _counter_spec(keys: tuple[str, ...], fault1970: bool) -> dict:
    """The aggregation spec shared by both grains (min/max are associative).

    Column order matches the historical agg-<year>.parquet files exactly
    (channel, day, n_events, n_alarm, n_num[, n_fault1970], num_*, s_*), so a
    freshly appended day is indistinguishable from the pre-existing rows.
    """
    spec = {
        "n_events": ("n_events", "sum"),
        "n_alarm": ("n_alarm", "sum"),
        "n_num": ("n_num", "sum"),
    }
    if fault1970:
        spec["n_fault1970"] = ("n_fault1970", "sum")
    spec.update({
        "num_sum": ("num_sum", "sum"),
        "num_sumsq": ("num_sumsq", "sum"),
        "num_min": ("num_min", "min"),
        "num_max": ("num_max", "max"),
    })
    spec.update({c: (c, "sum") for c in _STATE_COLS})
    return spec


def per_row_counts(
    df_raw: pd.DataFrame,
    dtype_map: Any,
    *,
    hour: bool = False,
    fault1970: bool = True,
) -> tuple[pd.DataFrame | None, dict]:
    """One chunk of journal rows -> additive counters, pre-reduced to the grain.

    Returns ``(partial, stats)``; ``partial`` is ``None`` when every row was
    filtered out. ``stats`` counts raw rows, coding artifacts and bad hours.
    """
    keys = HOUR_KEYS if hour else DAY_KEYS
    stats = {"raw": int(len(df_raw)), "invalid": 0, "bad_hour": 0}
    if df_raw.empty:
        return None, stats

    tr = df_raw["тревожное"].astype(str).str.strip().str.lower()
    df = df_raw[tr.isin(TRUE_TOKENS) | tr.isin(FALSE_TOKENS)]
    df = df[df["ид_канала_данных"].notna()]
    if df.empty:
        return None, stats
    tr = tr.loc[df.index]

    chan = df["ид_канала_данных"].astype(str)
    day = df["дата"].fillna("")
    val = df["значение_датчика"].fillna("")
    alarm = tr.isin(TRUE_TOKENS).astype(np.int32)
    num = pd.to_numeric(val, errors="coerce")

    if fault1970:
        f1970 = val.str.startswith("01.01.1970").to_numpy(np.int32)
        stats["invalid"] += int(f1970.sum())

    # drop coding artifacts from the numeric stats (REPORT.md §7): gas 327.68 /
    # negatives, thermal -3276 / 957..999 — they poison means and spreads
    inv = invalid_mask(chan.map(dtype_map), num)
    if inv.any():
        num = num.mask(inv)
        stats["invalid"] += int(inv.sum())

    counts = {
        "channel": chan.to_numpy(),
        "day": day.to_numpy(),
        "n_events": np.ones(len(df), np.int32),
        "n_alarm": alarm.to_numpy(),
        "n_num": num.notna().to_numpy(np.int32),
        "num_sum": num.fillna(0.0).to_numpy(np.float32),
        "num_sumsq": (num ** 2).fillna(0.0).to_numpy(np.float32),
        "num_min": num.to_numpy(np.float32),
        "num_max": num.to_numpy(np.float32),
    }
    if fault1970:
        counts["n_fault1970"] = f1970
    if hour:
        hour_of_day = pd.to_numeric(df["время"].fillna("").astype(str).str[:2].str.strip(),
                                    errors="coerce")
        stats["bad_hour"] += int(hour_of_day.isna().sum())
        counts["hour"] = hour_of_day.fillna(-1).astype(np.int32).to_numpy()
    value = val.to_numpy()
    for i in range(N_STATES):
        counts[f"s_{i}"] = (value == STATES[i]).astype(np.int8)

    part = pd.DataFrame(counts)
    # pre-reduce within the chunk: the same (channel, day) may be split across
    # chunks -> the final groupby in reduce_parts does the rest
    red = part.groupby(list(keys), sort=False).agg(**_counter_spec(keys, fault1970)).reset_index()
    return red, stats


def reduce_parts(parts: list[pd.DataFrame | None], keys: tuple[str, ...],
                 *, fault1970: bool = True) -> pd.DataFrame:
    """Concat per-chunk partials and aggregate to the requested grain."""
    frames = [p for p in parts if p is not None]
    if not frames:
        columns = list(keys) + list(_counter_spec(keys, fault1970))
        return pd.DataFrame(columns=columns)
    df = pd.concat(frames, ignore_index=True)
    return df.groupby(list(keys), sort=False).agg(
        **_counter_spec(keys, fault1970)
    ).reset_index()


def finalize(agg: pd.DataFrame, year: int, keys: tuple[str, ...],
             *, fault1970: bool = True, what: str = "channel-days") -> pd.DataFrame:
    """Cast dtypes, attach cabinet/object, drop the artifact spans."""
    if agg.empty:
        return agg
    agg["channel"] = agg["channel"].astype(str)
    agg["day"] = agg["day"].astype(str)
    if "hour" in keys:
        agg["hour"] = agg["hour"].astype(np.int32)
    int_cols = list(_INT_COLS) + (["n_fault1970"] if fault1970 else []) + list(_STATE_COLS)
    for c in int_cols:
        agg[c] = agg[c].astype(np.int32)
    for c in _FLOAT_COLS:
        agg[c] = agg[c].astype(np.float32)

    # cabinet/object per channel (unmatched = out-of-reference channels -> NaN)
    agg = agg.join(channel_ref()[["cabinet", "ид_объект"]], on="channel", how="left")
    agg["cabinet"] = agg["cabinet"].astype("category")
    agg["ид_объект"] = agg["ид_объект"].astype("category")

    for cab, d0, d1, yset in EXCLUDE_SPANS:
        if year in yset:
            mask = (agg["cabinet"] == cab) & agg["day"].between(d0, d1)
            if mask.any():
                n_drop = int(mask.sum())
                agg = agg[~mask].copy()
                print(f"  [exclude] {cab} {d0}..{d1} year={year}: dropped {n_drop:,} {what}", flush=True)
    return agg
