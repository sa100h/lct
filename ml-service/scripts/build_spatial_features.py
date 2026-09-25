"""Build cross-channel SPATIAL features (cabinet + object tier).

Reads:  ml-data/agg/agg-<year>.parquet (channel, day, n_alarm, s_0..s_25,
        cabinet, ид_объект) — one year at a time (3.8 GB box).
Writes: ml-data/features/spatial.parquet
        (channel, day, year, + 10 float32 spatial cols)
Join:   features-<cat>.parquet rows (channel, day) == agg rows (channel, day).

Definitions — NO label leakage (same trailing-window rule as the lag features):
- window = the 7 calendar days STRICTLY before day t (t-7 .. t-1); because the
  window is strictly before t, including the row's own channel in the numerator
  does NOT echo the label (self history is already captured by the lag feats).
- tier day-level activity = event counts over all reported rows of that tier
  on that day (a tier day aggregates every channel that reported that day,
  including the row's own channel). This is "how distressed is the whole
  cabinet / object right now" — the new cross-channel signal.

Columns (10):
  nbr_alarm7        sum of n_alarm over all cabinet channels, 7d (self incl.)
  nbr_crit7         count of critical-state rows over all cabinet channels, 7d
  nbr_alarm_rate7   nbr_alarm7 / (cabinet_channels) / 7
  nbr_crit_rate7    nbr_crit7 / (cabinet_channels) / 7
  nbr_affected7     fraction of the 7 window-days with ANY alarm in the cabinet
  nbr_failed_ratio7 fraction of the 7 window-days with ANY critical in cabinet
  obj_alarm7        sum of n_alarm over all object channels, 7d (self incl.)
  obj_alarm_rate7   obj_alarm7 / (object_channels) / 7
  obj_crit7         count of critical rows over all object channels, 7d
  obj_crit_rate7    obj_crit7 / (object_channels) / 7

Pitfalls honored:
- channel rows are scattered across row groups (NOT grouped) — the tier
  history is accumulated into per-year dicts, then windowed via searchsorted
  on day-ordinal arrays (strictly-previous window rule);
- days are calendar-day ordinals; a channel that did not report on day d
  contributes 0 events for that day (reported-days-only, same as base agg);
- rows whose cabinet / id_object is NaN get 0.0 for that tier's columns.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path("/home/junai/lct")
AGG_DIR = ROOT / "ml-data" / "agg"
OUT = ROOT / "ml-data" / "features" / "spatial.parquet"
W = 7  # trailing window in days (strictly before t)

SPATIAL_COLS = [
    "nbr_alarm7", "nbr_crit7", "nbr_alarm_rate7", "nbr_crit_rate7",
    "nbr_affected7", "nbr_failed_ratio7",
    "obj_alarm7", "obj_alarm_rate7", "obj_crit7", "obj_crit_rate7",
]


def critical_idx() -> list[int]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.ingest.aggregate import STATES

    vocab = json.loads((ROOT / "ml-data" / "vocab.json").read_text())
    idx = set()
    known = set(STATES)
    for cat in ("sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"):
        for name in vocab[cat]["critical"]:
            if name not in known:
                # vocab may contain states never emitted in the data (e.g. 'Штаф')
                continue
            idx.add(STATES.index(name))
    return sorted(idx)


class Tier:
    """Day-level history per tier key + trailing-window queries via suffix sums."""

    def __init__(self):
        self.days: dict = {}
        self.alarm: dict = {}
        self.crit: dict = {}
        self._suff: dict = {}

    def materialize(self) -> None:
        for key in list(self.days):
            da = np.asarray(self.days[key], dtype=np.int64)
            aa = np.asarray(self.alarm[key], dtype=np.float64)
            ca = np.asarray(self.crit[key], dtype=np.float64)
            # suffix sums: asa[i] = sum(aa[i:]); trailing 0 sentinel for diffs
            asa = np.concatenate((aa[::-1].cumsum()[::-1], [0.0]))
            csa = np.concatenate((ca[::-1].cumsum()[::-1], [0.0]))
            self._suff[key] = (da, asa, csa, aa, ca)
        self.alarm.clear()
        self.crit.clear()

    def window(self, key, day_ord: int):
        """(alarm_sum, crit_sum, alarm_days, crit_days) over the W calendar
        days strictly before day_ord. Zeros when the key is absent/NaN."""
        if key is None or key != key:
            return 0.0, 0.0, 0, 0
        t = self._suff.get(key)
        if t is None:
            return 0.0, 0.0, 0, 0
        da, asa, csa, aa, ca = t
        hi = int(np.searchsorted(da, day_ord, side="left"))     # first day >= day_ord
        lo = int(np.searchsorted(da, day_ord - W, side="left")) # first day >= day_ord - W
        if hi == 0 or hi <= lo:
            return 0.0, 0.0, 0, 0
        # indices [lo, hi) = the existing days in [day_ord - W, day_ord - 1]
        a_sum = float(asa[lo] - asa[hi])
        c_sum = float(csa[lo] - csa[hi])
        a_days = int((aa[lo:hi] > 0).sum())
        c_days = int((ca[lo:hi] > 0).sum())
        return a_sum, c_sum, a_days, c_days


def build_year(year: int, crit: list[int]) -> pd.DataFrame:
    t0 = time.time()
    pf = pq.ParquetFile(AGG_DIR / f"agg-{year}.parquet")
    n = pf.metadata.num_rows
    crit_cols = [f"s_{k}" for k in crit]
    need = ["channel", "day", "n_alarm", "cabinet", "ид_объект"] + crit_cols

    chan = np.empty(n, dtype=object)
    days = np.empty(n, dtype=np.int64)
    cabs = np.empty(n, dtype=object)
    objs = np.empty(n, dtype=object)
    alarm = np.empty(n, dtype=np.float64)
    crit_rows = np.empty(n, dtype=np.int64)

    cab_agg: dict = {}
    obj_agg: dict = {}
    off = 0
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i, columns=need)
        s = rg.to_pandas()
        gn = len(s)
        start, end = off, off + gn
        off = end
        c = s["channel"].to_numpy()
        d = pd.to_datetime(s["day"]).values.astype("datetime64[D]").astype(np.int64)
        ca = s["cabinet"].to_numpy()
        ob = s["ид_объект"].to_numpy()
        al = s["n_alarm"].to_numpy().astype(np.float64)
        cr = (s[crit_cols].sum(axis=1) > 0).astype(np.int64).to_numpy()

        chan[start:end] = c
        days[start:end] = d
        cabs[start:end] = ca
        objs[start:end] = ob
        alarm[start:end] = al
        crit_rows[start:end] = cr

        # tier day-level aggregation: (key, day) -> [alarm_sum, crit_count]
        for j in range(gn):
            dj, aj, k2 = d[j], al[j], cr[j]
            k = ca[j]
            if k == k:
                dd = cab_agg.get(k)
                if dd is None:
                    cab_agg[k] = {dj: [aj, k2]}
                else:
                    v = dd.get(dj)
                    if v is None:
                        dd[dj] = [aj, k2]
                    else:
                        v[0] += aj
                        v[1] += k2
            k = ob[j]
            if k == k:
                dd = obj_agg.get(k)
                if dd is None:
                    obj_agg[k] = {dj: [aj, k2]}
                else:
                    v = dd.get(dj)
                    if v is None:
                        dd[dj] = [aj, k2]
                    else:
                        v[0] += aj
                        v[1] += k2
        del rg

    cab = Tier()
    obj = Tier()
    for key, dd in cab_agg.items():
        cab.days[key] = sorted(dd)
        cab.alarm[key] = [dd[dj][0] for dj in cab.days[key]]
        cab.crit[key] = [dd[dj][1] for dj in cab.days[key]]
    for key, dd in obj_agg.items():
        obj.days[key] = sorted(dd)
        obj.alarm[key] = [dd[dj][0] for dj in obj.days[key]]
        obj.crit[key] = [dd[dj][1] for dj in obj.days[key]]
    cab.materialize()
    obj.materialize()

    # neighbor sizes for the rate columns (distinct channels per tier, this year)
    chan_cab: dict = {}
    obj_chan: dict = {}
    for j in range(n):
        k = cabs[j]
        if k == k:
            chan_cab.setdefault(k, set()).add(chan[j])
        k = objs[j]
        if k == k:
            obj_chan.setdefault(k, set()).add(chan[j])

    out = np.zeros((n, len(SPATIAL_COLS)), dtype=np.float32)
    for j in range(n):
        k = cabs[j]
        cs = max(0, len(chan_cab[k]) - 1) if k == k else 0
        da, ca_, ad, cd = cab.window(k, int(days[j]))
        if cs:
            out[j, 0] = da
            out[j, 1] = ca_
            out[j, 2] = da / (cs * W)
            out[j, 3] = ca_ / (cs * W)
            out[j, 4] = ad / W
            out[j, 5] = cd / W
        k = objs[j]
        os_ = max(0, len(obj_chan[k]) - 1) if k == k else 0
        ao, co, _, _ = obj.window(k, int(days[j]))
        if os_:
            out[j, 6] = ao
            out[j, 7] = ao / (os_ * W)
            out[j, 8] = co
            out[j, 9] = co / (os_ * W)

    df = pd.DataFrame(
        {
            "channel": [str(c) for c in chan],
            "day": pd.to_datetime(days, unit="D"),
            "year": [year] * n,
            **{c: out[:, i].astype(np.float32) for i, c in enumerate(SPATIAL_COLS)},
        }
    )
    nz = float((out[:, 0] != 0).mean())
    print(f"{year}: rows={n} nonzero_nbr_alarm={nz:.3f} {time.time()-t0:.1f}s", flush=True)
    return df


def main() -> None:
    t0 = time.time()
    crit = critical_idx()
    print("critical idx:", crit, flush=True)
    parts = [build_year(y, crit) for y in range(2019, 2027)]
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(OUT, index=False)
    print(f"WROTE {OUT} rows={len(df)} cols={len(df.columns)} {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
