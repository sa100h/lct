"""One-pass, resumable scan of the full SMVU journal -> state-scan.json.

Ground truth for the pipeline-agreement questions:
  * full state vocabulary actually present vs the organizer's
    справочник_состояний.csv (missed states / unknown states);
  * numeric distribution per sensor type + full gas histogram
    (confirms 1% methane alarm threshold, 5-15% ignition band);
  * the 01.01.1970 timestamp artifacts (count, channels, types, exact values);
  * per-state тревожное=true breakdown.

Streaming 4M-row chunks, vectorized groupby accumulated into global dicts.
Writes a partial state-scan.json after EVERY year — a kill loses at most one
year. Resume: years present in the output json are skipped.
"""
from __future__ import annotations
import json, time
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

from app.config import ANALYSIS_DIR, DATA_DIR, EXTRACTED_DIR

EX = EXTRACTED_DIR
OUT = ANALYSIS_DIR / "state-scan.json"
COLS = ["ид_канала_данных", "тревожное", "значение_датчика"]
CHUNK = 4_000_000
TRUE_TOKENS = {"t", "true", "1", "yes"}
FALSE_TOKENS = {"f", "false", "0", "no"}

# gas histogram bins: %volume methane. <0, fine 0-1 grid, 1-2, 2-5, 5-15, 15-100, >100
GAS_BINS = [-np.inf, -1e-9, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0, 1.5, 2.0, 3.0, 5.0, 15.0, 100.0, np.inf]

ref = pd.read_csv(DATA_DIR / "справочник_каналов_датчиков.csv", dtype=str)
type_map = ref.set_index("ид_канала_данных")["тип_датчика"].to_dict()
sd = pd.read_csv(DATA_DIR / "справочник_состояний.csv")
dict_states = set(sd["название_состояния"].unique())
alarm_dict = set(sd[sd["тревожное"] == "true"]["название_состояния"].unique())

# --- global accumulators -------------------------------------------------
state_total: Counter = Counter()          # state -> rows
state_alarm: Counter = Counter()          # state -> rows where тревожное=true
state_type: Counter = Counter()           # (state, type) -> rows
n1970: Counter = Counter()                # exact 1970 value string -> rows
n1970_type: Counter = Counter()           # (1970 value, type) -> rows
num_stat: dict[str, dict] = {}            # type -> {n,min,max,sum}
gas_hist = np.zeros(len(GAS_BINS) - 1, np.int64)
n_raw = n_kept = 0


def add_num_stat(ty: str, a: np.ndarray) -> None:
    st = num_stat.setdefault(ty, {"n": 0, "min": float("inf"), "max": float("-inf"), "sum": 0.0})
    st["n"] += len(a)
    st["min"] = min(st["min"], float(a.min()))
    st["max"] = max(st["max"], float(a.max()))
    st["sum"] += float(a.sum())


def scan_year(f: Path) -> int:
    """Scan one year file. Returns seconds spent."""
    global n_raw, n_kept, gas_hist
    t0 = time.time()
    for chunk in pd.read_csv(f, usecols=COLS, dtype=str, chunksize=CHUNK, low_memory=False):
        n_raw_l = len(chunk)
        tr = chunk["тревожное"].str.strip().str.lower()
        keep = (tr.isin(TRUE_TOKENS) | tr.isin(FALSE_TOKENS)) & chunk["ид_канала_данных"].notna()
        chunk = chunk[keep]
        if chunk.empty:
            n_raw += n_raw_l
            continue
        val = chunk["значение_датчика"].fillna("")
        alarm = tr.loc[chunk.index].isin(TRUE_TOKENS)
        ty = chunk["ид_канала_данных"].astype(str).map(type_map).fillna("(нет в справ.)")
        num = pd.to_numeric(val, errors="coerce")

        for s, c in val.value_counts().items():
            state_total[s] += int(c)
        if alarm.any():
            for s, c in val[alarm].value_counts().items():
                state_alarm[s] += int(c)
        for (s, t), c in pd.DataFrame({"v": val.to_numpy(), "t": ty.to_numpy()}).groupby(["v", "t"]).size().items():
            state_type[(s, t)] += int(c)

        mask1970 = val.str.startswith("01.01.1970")
        if mask1970.any():
            for s, c in val[mask1970].value_counts().items():
                n1970[s] += int(c)
            for (s, t), c in pd.DataFrame({"v": val[mask1970].to_numpy(), "t": ty[mask1970].to_numpy()}).groupby(["v", "t"]).size().items():
                n1970_type[(s, t)] += int(c)

        gn = num.dropna()
        tser = pd.Series(ty.to_numpy(), index=chunk.index)
        for t, grp in gn.groupby(tser.loc[gn.index].to_numpy()):
            add_num_stat(t, grp.to_numpy())
        gas = num[ty == "Газовый датчик"].dropna().to_numpy()
        if len(gas):
            gas_hist += np.histogram(gas, bins=GAS_BINS)[0]
        n_raw += n_raw_l
        n_kept += len(chunk)
    return round(time.time() - t0, 1)


def snapshot() -> dict:
    return {
        "n_raw": int(n_raw), "n_kept": int(n_kept),
        "year_progress": list(year_done),
        "state_total": {k: int(v) for k, v in state_total.items()},
        "state_alarm": {k: int(v) for k, v in state_alarm.items()},
        "state_type": {f"{s}||{t}": int(c) for (s, t), c in state_type.items()},
        "n1970": {k: int(v) for k, v in n1970.items()},
        "n1970_type": {f"{s}||{t}": int(c) for (s, t), c in n1970_type.items()},
        "num_stats": num_stat,
        "gas_bins": [None if np.isinf(b) else b for b in GAS_BINS],
        "gas_hist": [int(x) for x in gas_hist],
        "dict_states": sorted(dict_states),
        "dict_alarm_states": sorted(alarm_dict),
        "state_not_in_dict": sorted(set(state_total) - dict_states),
        "dict_state_never_seen": sorted(dict_states - set(state_total)),
        "alarm_state_not_in_dict": sorted(set(state_alarm) - dict_states),
    }


year_done: list[str] = []


def main() -> None:
    years = sorted(p.name for p in EX.iterdir() if p.is_dir() and p.name.isdigit())
    done = set()
    if OUT.exists():
        try:
            done = set(json.loads(OUT.read_text())["year_progress"])
        except Exception:
            done = set()
    # NOTE: resuming from a partial json does NOT restore the in-memory
    # counters, so a resumed run only contains post-resume years' stats.
    # If this is a FRESH full run, delete the partial json first.
    for y in years:
        f = EX / y / f"ext-journal-{y}.csv"
        if not f.exists():
            continue
        if y in done:
            print(f"{y}: skip (already in json)", flush=True)
            continue
        t = scan_year(f)
        year_done.append(y)
        OUT.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=1))
        print(f"{y}: {t}s saved {OUT.stat().st_size/1e6:.1f}MB", flush=True)
    OUT.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=1))
    print("ALL DONE ->", OUT, f"({OUT.stat().st_size/1e6:.1f}MB)", flush=True)
    seen = set(state_total)
    print(f"states seen={len(seen)} in_dict={len(seen & dict_states)} "
          f"not_in_dict={len(seen - dict_states)} dict_never_seen={len(dict_states - seen)}")
    print("not_in_dict:", sorted(set(state_total) - dict_states)[:60])
    print("dict_never_seen:", sorted(dict_states - set(state_total)))


if __name__ == "__main__":
    main()
