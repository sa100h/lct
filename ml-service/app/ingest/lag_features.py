"""Canonical per-channel lag features — ONE module for train AND serve.

Train/serve parity is the whole point: the exact same formulas produce the
11 lag columns in the training parquet (`add_lag_features`) and the 11 lag
values the prediction engine computes at serve time from the observation
store (`lag_values_for_history`). A regression test locks the parity.

Formulas (inherited verbatim from the experiment `scripts/_lag_model.py`,
which produced ml-data/lags/lag-model-results.json):

- history = the channel's STRICTLY PREVIOUS observation rows, sorted by day.
- since_prev: days between this observation and the previous one (NaN for
  the first row of a channel — the documented "no history" convention,
  identical to serve; clipped to [0, 999]).
- since_first: age of the channel in days from its first observation
  (NaN for the first row; clipped to [0, 9999]).
- label_lag1/label_lag2: label at the 1st / 2nd previous observation,
  NaN while fewer than that many observations exist.
- fail_rate_prevW / n_obs_prevW (W = 30/90/365): share / count of
  observations with d[t] - d[p] <= W (two-pointer, strictly previous rows
  p..t-1, so d[t] - d[p] > W is the exclusion test; a gap at the edge is
  fine — every included row is strictly before t). NaN when the window
  holds no observation (no history).
- since_last_fail / since_last_ok: number of observations since the last
  failed / ok day, update-after-emit, MISSING = 9999.0 sentinel when no
  such observation exists yet. The sentinel (not NaN) is the convention
  for "no such event yet" on BOTH train and serve (LightGBM treats both
  fine; the sentinel matches the experiment exactly).

Serve semantics: the decision day `t` (e.g. today) is NOT part of the
history; history rows with d >= t are excluded (no same-day leakage).
A subject with an empty history gets NaN in since_prev/since_first/
label_lag1/label_lag2/fail_rate_prev* (and n_obs_prev* = 0.0, the true
count), plus the since_last_* 9999.0 sentinels — the same values the
first observation row of a channel carries in training (see below).
Train follows the same convention: the FIRST observation row of each
channel (no strictly-previous history) is NaN in exactly those slots the
serve empty-history vector is NaN in. So a channel's row 0 in training
carries the same "no history" signature the live store emits for a fresh
subject — LightGBM learns one default direction for both.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Canonical 11 names — the order is part of the train/serve contract.
LAG_FEATURES: list[str] = [
    "since_prev",
    "since_first",
    "label_lag1",
    "label_lag2",
    "fail_rate_prev30",
    "fail_rate_prev90",
    "n_obs_prev30",
    "n_obs_prev90",
    "n_obs_prev365",
    "since_last_fail",
    "since_last_ok",
]
LAG_SET = frozenset(LAG_FEATURES)

MISSING = 9999.0  # sentinel: "no prior event of this kind yet" (fixed by the experiment)
WINDOWS = (30, 90, 365)

META_COLS = ("channel", "day", "year", "label")


def day_ordinal(ts) -> int:
    """Epoch day number for a timestamp-like input (serving side).

    Day ordinals on train and serve come from different origins but only
    DIFFERENCES are ever used (since_*, window edges), so an epoch day is
    safe and makes train/serve comparable.
    """
    return int(pd.Timestamp(ts).tz_localize(None).timestamp() // 86400)


def _group_lags(d: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    """Lag features for ONE channel, sorted by day (m rows, m>=1).

    d: int64 day ordinals (strictly increasing), y: float64 labels.
    Returns {name: float32[m]} with exactly the experiment's formulas.
    """
    m = len(d)
    out: dict[str, np.ndarray] = {k: np.empty(m, dtype=np.float32) for k in LAG_FEATURES}
    if m == 0:
        for k in LAG_FEATURES:
            out[k] = np.empty(0, dtype=np.float32)
        return out

    first = int(d[0])

    # --- strictly-previous since_last_fail / since_last_ok (update after emit) ---
    last_fail = np.full(m, MISSING, dtype=np.float32)
    last_ok = np.full(m, MISSING, dtype=np.float32)
    lf = lo = -1
    for t in range(m):
        last_fail[t] = (t - lf) if lf >= 0 else MISSING
        last_ok[t] = (t - lo) if lo >= 0 else MISSING
        if y[t] == 1:
            lf = t
        else:
            lo = t

    # --- lag states ---
    lab_lag1 = np.full(m, np.nan, dtype=np.float32)
    lab_lag2 = np.full(m, np.nan, dtype=np.float32)
    if m > 1:
        lab_lag1[1:] = y[:-1]
    if m > 2:
        lab_lag2[2:] = y[:-2]

    # --- windowed (two-pointer, strictly previous) ---
    prefix = np.empty(m + 1, dtype=np.float64)
    prefix[0] = 0.0
    prefix[1:] = np.cumsum(y)
    win: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for W in WINDOWS:
        cnt = np.zeros(m, dtype=np.int32)
        rate = np.full(m, np.nan, dtype=np.float32)  # NaN = no history in window (serve parity)
        p = 0
        for t in range(m):
            while p < t and d[t] - d[p] > W:
                p += 1
            c = t - p
            cnt[t] = c
            if c:
                rate[t] = (prefix[t] - prefix[p]) / c
        win[W] = (cnt, rate)

    sp = np.full(m, np.nan, dtype=np.float32)
    if m > 1:
        sp[1:] = np.clip(np.diff(d), 0, 999)
    sf = np.full(m, np.nan, dtype=np.float32)
    if m > 1:
        sf[1:] = np.clip(d[1:] - first, 0, 9999)
    out["since_prev"] = sp
    out["since_first"] = sf
    out["label_lag1"] = lab_lag1
    out["label_lag2"] = lab_lag2
    out["fail_rate_prev30"] = win[30][1]
    out["fail_rate_prev90"] = win[90][1]
    out["n_obs_prev30"] = win[30][0].astype(np.float32)
    out["n_obs_prev90"] = win[90][0].astype(np.float32)
    out["n_obs_prev365"] = win[365][0].astype(np.float32)
    out["since_last_fail"] = last_fail
    out["since_last_ok"] = last_ok
    return out


def lag_features_for_history(d: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    """Vectorized training side: per-row lag features for a sorted channel panel.

    d: day ordinals (int, strictly increasing), y: labels (float, 0/1).
    Same formulas as the experiment's group loop — this is the body of
    `build_lags` in scripts/_lag_model.py, extracted.
    """
    return _group_lags(np.asarray(d), np.asarray(y, dtype=np.float64))


def lag_values_for_history(d: np.ndarray, y: np.ndarray, t: int) -> dict[str, float]:
    """Serving side: 11 lag values for a decision day `t`.

    d: day ordinals of the subject's STRICTLY PREVIOUS history (sorted;
    rows with day >= t are excluded by the caller or here), y: their labels.
    t: the decision day's ordinal (e.g. today, UTC).

    Parity with training: with history = rows 0..t-1 of a channel, these
    values equal the row-t values of `lag_features_for_history` (m>=1).
    Empty history -> since_prev/since_first/label_lag*/fail_rate_* = NaN,
    n_obs_prev* = 0.0 (true count), since_last_fail/ok = MISSING sentinel.
    """
    d = np.asarray(d)
    y = np.asarray(y, dtype=np.float64)
    # Decision day is NOT history: exclude same-day/future rows (no leakage).
    if d.size:
        keep = d < t
        d, y = d[keep], y[keep]
    m = d.size

    if m == 0:
        return {
            **dict.fromkeys(
                [k for k in LAG_FEATURES if k not in ("since_last_fail", "since_last_ok", "n_obs_prev30", "n_obs_prev90", "n_obs_prev365")],
                float("nan"),
            ),
            "n_obs_prev30": 0.0,
            "n_obs_prev90": 0.0,
            "n_obs_prev365": 0.0,
            "since_last_fail": float(MISSING),
            "since_last_ok": float(MISSING),
        }

    # --- since_last_fail / since_last_ok over history (m = count of prior obs) ---
    last_fail = np.full(m, MISSING, dtype=np.float32)
    last_ok = np.full(m, MISSING, dtype=np.float32)
    lf = lo = -1
    for i in range(m):
        last_fail[i] = (i - lf) if lf >= 0 else MISSING
        last_ok[i] = (i - lo) if lo >= 0 else MISSING
        if y[i] == 1:
            lf = i
        else:
            lo = i

    # decision-day reference: t replaces row index m (next row), so the
    # "observations since last event" count is m - lf (== t - lf in training,
    # where the decision row is row t of the sorted group).
    val_fail = float(MISSING) if lf < 0 else float(m - lf)
    val_ok = float(MISSING) if lo < 0 else float(m - lo)

    prefix = np.empty(m + 1, dtype=np.float64)
    prefix[0] = 0.0
    prefix[1:] = np.cumsum(y)

    vals: dict[str, float] = {}
    vals["since_prev"] = float(np.clip(t - int(d[-1]), 0, 999))
    vals["since_first"] = float(np.clip(t - int(d[0]), 0, 9999))
    vals["label_lag1"] = float(y[-1])
    vals["label_lag2"] = float(y[-2]) if m > 1 else float("nan")

    win: dict[int, tuple[int, float]] = {}
    for W in WINDOWS:
        p = 0
        while p < m and t - int(d[p]) > W:
            p += 1
        c = m - p
        rate = float((prefix[m] - prefix[p]) / c) if c else float("nan")  # NaN when the window is empty (train parity)
        win[W] = (c, rate)

    vals["fail_rate_prev30"] = win[30][1]
    vals["fail_rate_prev90"] = win[90][1]
    vals["n_obs_prev30"] = float(win[30][0])
    vals["n_obs_prev90"] = float(win[90][0])
    vals["n_obs_prev365"] = float(win[365][0])
    vals["since_last_fail"] = val_fail
    vals["since_last_ok"] = val_ok
    return vals


def read_panel_meta(parquet_path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Stream (channel, day, year, label) from a features parquet, original order.

    Returns (ch object array, d_ord int64 epoch days, year int, label float64).
    """
    path = Path(parquet_path)
    pf = pq.ParquetFile(path)
    ch_p, day_p, yr_p, lab_p = [], [], [], []
    try:
        for i in range(pf.metadata.num_row_groups):
            rg = pf.read_row_group(i, columns=list(META_COLS))
            ch_p.append(rg.column("channel").to_numpy())
            day_p.append(rg.column("day").to_numpy())
            yr_p.append(rg.column("year").to_numpy())
            lab_p.append(rg.column("label").to_numpy())
    finally:
        pf.close()
    ch = np.concatenate(ch_p)
    day = pd.to_datetime(np.concatenate(day_p))
    d_ord = ((day - day.min()) // pd.Timedelta(days=1)).to_numpy(np.int64)
    yr = np.concatenate(yr_p)
    lab = np.concatenate(lab_p).astype(np.float64)
    return ch, d_ord, yr, lab


def compute_lags(parquet_path: str | Path) -> dict:
    """Panel-level lags in ORIGINAL row order (training side, full pass).

    Returns {name: float32[n]} for all 11 LAG_FEATURES, rows in file order —
    the drop-in replacement for `build_lags` in scripts/_lag_model.py.
    """
    ch, d_ord, yr, lab = read_panel_meta(parquet_path)
    n = len(ch)

    codes = pd.Series(ch).astype("category").cat.codes.to_numpy()
    order = np.lexsort((d_ord, codes))  # sort by channel, then day
    cs = codes[order]
    dd = d_ord[order]
    yy = lab[order]

    gstart = np.r_[0, np.flatnonzero(np.diff(cs)) + 1]
    n_groups = len(gstart)

    out = {k: np.empty(n, dtype=np.float32) for k in LAG_FEATURES}
    for gi in range(n_groups):
        s, e = gstart[gi], (gstart[gi + 1] if gi + 1 < n_groups else n)
        m = e - s
        if m == 0:
            continue
        gl = _group_lags(dd[s:e], yy[s:e])
        idx = order[s:e]
        for k in LAG_FEATURES:
            out[k][idx] = gl[k]
    return out


def add_lag_features(parquet_path: str | Path) -> Path:
    """Append the 11 lag columns to a features parquet (in place, idempotent).

    Rewrites the file as <name>.withlags.parquet -> atomically replaces the
    original. Existing lag columns (from a previous pass) are dropped first,
    so re-running never duplicates. Base columns are copied through verbatim.
    """
    path = Path(parquet_path)
    lags = compute_lags(path)
    n = len(next(iter(lags.values())))

    pf = pq.ParquetFile(path)
    existing = list(pf.schema_arrow.names)
    base_cols = [c for c in existing if c not in LAG_SET]
    tmp = path.with_suffix(path.suffix + ".withlags")

    writer = None
    offset = 0
    try:
        for i in range(pf.metadata.num_row_groups):
            table = pf.read_row_group(i)
            sub = table.select(base_cols)
            start, end = offset, offset + sub.num_rows
            offset = end
            for k in LAG_FEATURES:
                sub = sub.append_column(k, pa_array_from_numpy(lags[k][start:end]))
            if writer is None:
                schema = sub.schema
                writer = pq.ParquetWriter(tmp, schema)
            writer.write_table(sub)
            del table
    finally:
        pf.close()
        if writer is not None:
            writer.close()

    if offset != n:
        raise RuntimeError(f"lag rewrite wrote {offset} rows, expected {n}")
    tmp.replace(path)
    return path


def pa_array_from_numpy(arr: np.ndarray):
    import pyarrow as pa

    return pa.array(arr, type=pa.float32())
