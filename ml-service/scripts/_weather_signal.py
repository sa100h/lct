"""Does Moscow weather add signal to the LCT sensor-failure model?

Two-phase, leak-free analysis on the EXACT shipped split (train<2026, test=2026).
Memory-safe: streams feature parquet row-group by row-group, one float32 buffer,
mirrors app/models/baseline.py.

Phase 1 (cheap, daily): per-day failure-rate of sensor-failure channels,
  corr with each weather var, and PARTIAL corr controlling for month_sin/cos
  (the seasonality the model already has). Output: weather/weather-daily-signal.csv
Phase 2 (decisive, model-level):
  - single weather-var AUC on 2026 (each var alone)
  - HGB AUC/AP/P/R  baseline(188) vs baseline+weather, identical hyperparams
  - top feature importances of the +weather model
Output: prints a report; also writes weather/weather-model-results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

FEAT = Path("/home/junai/lct/ml-data/features/features-sensor-failure.parquet")
WX = Path("/home/junai/lct/ml-data/weather/weather-moscow-daily.parquet")
META = {"channel", "day", "year", "label"}
TEST_YEAR = 2026
MAX_TRAIN = 500_000

HGB = dict(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
           l2_regularization=1.0, class_weight="balanced", random_state=42)

wx_cols = [c for c in pq.read_schema(WX).names if c != "day"]
N_FEAT = len([c for c in pq.read_schema(FEAT).names if c not in META])


def load_weather() -> pd.DataFrame:
    df = pq.read_table(WX).to_pandas()
    df["day"] = pd.to_datetime(df["day"].astype(str))
    df = df.set_index("day").sort_index()
    # de-dupe on date in case of any clock mismatch (keep first)
    df = df[~df.index.duplicated(keep="first")]
    return df


def stream_matrix(tr_sample_ratio: float):
    """Stream the feature table ONCE; build two bounded buffers separately:
      - train: 2019-01-01..2025-12-31, subsampled to tr_sample_ratio of rows
      - test : 2026-01-01.. (the held-out year)

    Returns (Xtr, ytr, daytr_dt64, Xte, yte, dayte_dt64). Never holds all 8 years.
    """
    pf = pq.ParquetFile(FEAT)
    names = [c for c in pf.schema_arrow.names if c not in META]
    n_feat = len(names)
    load_cols = names + ["day", "year", "label"]
    n_rgs = pf.metadata.num_row_groups

    # pass 1: stream year column to size train (so we know how much to sample)
    yr = np.concatenate(
        [pf.read_row_group(i, columns=["year"]).column(0).to_numpy() for i in range(n_rgs)]
    )
    pf.close(); pf = pq.ParquetFile(FEAT)
    n_rgs = pf.metadata.num_row_groups
    n_tr = int((yr < TEST_YEAR).sum())
    keep_ratio = min(1.0, MAX_TRAIN / max(1, n_tr))
    del yr
    print(f"raw train rows={n_tr:,} -> keep {keep_ratio:.1%} (target {MAX_TRAIN:,})")

    ncol = n_feat
    tr_x = []  # list of (bool mask, X_chunk) buffered per row-group
    te_X = []
    pos = 0
    # first pass for train sizing is done; single pass now building both
    rng = np.random.default_rng(42)
    tr_parts = []   # [X0, y0, d0, X1, y1, d1, ...]  (3-tuples)
    te_parts = []   # [X0, y0, d0, X1, y1, d1, ...]  (3-tuples)
    for i in range(n_rgs):
        rg = pf.read_row_group(i, columns=load_cols)
        ycol = rg.column("year").to_numpy()
        trm = ycol < TEST_YEAR
        tem = ycol == TEST_YEAR
        if trm.any():
            sub = rg.filter(pa.array(trm))
            k = sub.num_rows
            if k > 0 and keep_ratio < 1.0:
                pick = rng.random(k) < keep_ratio
                if not pick.any():
                    del rg; continue
                sub = sub.filter(pa.array(pick))
                k = sub.num_rows
            Xc = np.empty((k, ncol), dtype=np.float32)
            for j, n in enumerate(names):
                Xc[:, j] = sub.column(n).to_numpy()
            tr_parts.append(Xc)
            tr_parts.append(sub.column("label").to_numpy())
            tr_parts.append(pd.to_datetime(sub.column("day").to_numpy()).to_numpy())
        if tem.any():
            sub = rg.filter(pa.array(tem))
            k = sub.num_rows
            Xc = np.empty((k, ncol), dtype=np.float32)
            for j, n in enumerate(names):
                Xc[:, j] = sub.column(n).to_numpy()
            te_parts.append(Xc)
            te_parts.append(sub.column("label").to_numpy())
            te_parts.append(pd.to_datetime(sub.column("day").to_numpy()).to_numpy())
        del rg
    # interleave: parts = [X0, y0, d0, X1, y1, d1, ...]
    Xtr = np.concatenate([tr_parts[i] for i in range(0, len(tr_parts), 3)], axis=0)
    ytr = np.concatenate([tr_parts[i] for i in range(1, len(tr_parts), 3)])
    daytr = np.concatenate([tr_parts[i] for i in range(2, len(tr_parts), 3)])
    del tr_parts
    Xte = np.concatenate([te_parts[i] for i in range(0, len(te_parts), 3)], axis=0)
    yte = np.concatenate([te_parts[i] for i in range(1, len(te_parts), 3)])
    dayte = np.concatenate([te_parts[i] for i in range(2, len(te_parts), 3)])
    del te_parts
    return Xtr, ytr, daytr, Xte, yte, dayte


def main() -> None:
    print("== loading weather ==")
    wx = load_weather()
    print(f"weather: {len(wx)} days x {len(wx_cols)} vars")

    # ---------- PHASE 1: daily-level, partial for season ----------
    print("\n== Phase 1: daily failure-rate vs weather (partialled for month) ==")
    pf = pq.ParquetFile(FEAT)
    # stream just (day, label) -> per-day aggregate. memory-safe.
    day_p = []; lab_p = []
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i, columns=["day", "label"])
        day_p.append(rg.column("day").to_numpy())
        lab_p.append(rg.column("label").to_numpy())
    day = np.concatenate(day_p); lab = np.concatenate(lab_p)
    del day_p, lab_p
    # day is a string array; build per-day failure rate
    tmp = pd.DataFrame({"day": day.astype(str), "lab": lab})
    tmp["day"] = pd.to_datetime(tmp["day"])
    g = tmp.groupby("day").agg(n_active=("lab", "size"), n_fail=("lab", "sum")).reset_index()
    g["fail_rate"] = g["n_fail"] / g["n_active"]
    wx_reset = wx.reset_index()  # 'day' is datetime now
    g = g.merge(wx_reset, on="day", how="left")
    g = g[g["n_active"] >= 50]  # stable daily denominator
    g = g[~g[wx_cols].isna().any(axis=1)]  # drop days missing weather
    g.to_csv("/home/junai/lct/ml-data/weather/weather-daily-signal.csv", index=False)

    # season dummies: month sin/cos of the day
    m = g["day"].dt.month
    ms = np.sin(2 * np.pi * (m - 1) / 12)
    mc = np.cos(2 * np.pi * (m - 1) / 12)
    Xs = np.column_stack([np.ones(len(g)), ms, mc])
    resid = lambda z: (z - Xs @ np.linalg.lstsq(Xs, z, rcond=None)[0])
    fr_res = resid(g["fail_rate"].to_numpy())
    rows = []
    for c in wx_cols:
        z = g[c].to_numpy()
        z_res = resid(z)
        # partial corr = corr of residuals
        pr = np.corrcoef(fr_res, z_res)[0, 1]
        corr_raw = np.corrcoef(fr_res + (g["fail_rate"].to_numpy() - fr_res), z)[0, 1]  # raw-ish
        # simpler raw corr with fail_rate
        raw = np.corrcoef(g["fail_rate"].to_numpy(), z)[0, 1]
        rows.append({"var": c, "raw_corr": round(float(raw), 4),
                     "partial_corr_vs_season": round(float(pr), 4)})
    tbl = pd.DataFrame(rows).sort_values("partial_corr_vs_season",
                                         key=lambda s: s.abs(), ascending=False)
    print(tbl.to_string(index=False))
    print("\n(daily failure-rate: "
          f"mean={g['fail_rate'].mean():.3f} std={g['fail_rate'].std():.3f}, "
          f"{len(g)} days used; N_active min={int(g['n_active'].min())})")

    # ---------- PHASE 2: model-level ----------
    print("\n== Phase 2: HGB baseline vs +weather on train<2026 / test=2026 ==")
    Xtr, ytr, daytr, Xte, yte, dayte = stream_matrix(MAX_TRAIN)
    print(f"train rows={len(ytr):,}  test rows={len(yte):,}")

    # weather join: per-row dates -> per-row weather row (duplicate days OK, .loc
    # returns one row per label; raises KeyError on any missing date -> loud, not silent)
    def weather_for(dates: np.ndarray) -> np.ndarray:
        idx = pd.DatetimeIndex(dates)
        aligned = wx.loc[idx, wx_cols]
        assert aligned.shape[0] == len(dates), "weather row-count mismatch"
        return aligned.to_numpy(dtype=np.float32)

    W_te = weather_for(dayte)
    W_tr = weather_for(daytr)
    n_w = len(wx_cols)

    results = {}

    # (a) single weather-var AUC on 2026 (each alone; max(auc,1-auc) = signal magnitude)
    print("\n-- single weather var AUC on 2026 (label=sensor-failure) --")
    single_mag = {}
    for j, c in enumerate(wx_cols):
        v = W_te[:, j]
        if np.unique(v).size < 2:
            continue
        a = roc_auc_score(yte, v)
        single_mag[c] = round(float(max(a, 1 - a)), 4)
    srt = sorted(single_mag.items(), key=lambda kv: -kv[1])
    for c, v in srt:
        print(f"  {c:28s} AUC={v:.4f}")

    # (b) baseline HGB (188 feats)
    m0 = HistGradientBoostingClassifier(**HGB)
    m0.fit(Xtr, ytr)
    p0 = m0.predict_proba(Xte)[:, 1]
    pr0 = (p0 >= 0.5).astype(int)
    results["baseline"] = {
        "n_feat": 188,
        "auc": round(float(roc_auc_score(yte, p0)), 4),
        "ap": round(float(average_precision_score(yte, p0)), 4),
        "precision": round(float(precision_score(yte, pr0, zero_division=0)), 4),
        "recall": round(float(recall_score(yte, pr0, zero_division=0)), 4),
    }
    print("\nbaseline(188):", results["baseline"])

    # (c) baseline + weather — release baseline-only arrays BEFORE fitting to cut
    # peak RSS (this box has ~3GB free; Xtr alone is ~375MB at 500k rows)
    del m0, p0, pr0
    import gc
    Xtr_w = np.empty((len(Xtr), N_FEAT + n_w), dtype=np.float32)
    Xtr_w[:, :N_FEAT] = Xtr
    Xtr_w[:, N_FEAT:] = W_tr
    del Xtr, W_tr
    Xte_w = np.empty((len(Xte), N_FEAT + n_w), dtype=np.float32)
    Xte_w[:, :N_FEAT] = Xte
    Xte_w[:, N_FEAT:] = W_te
    del Xte, W_te, daytr, dayte
    gc.collect()
    m1 = HistGradientBoostingClassifier(**HGB)
    m1.fit(Xtr_w, ytr)
    p1 = m1.predict_proba(Xte_w)[:, 1]
    pr1 = (p1 >= 0.5).astype(int)
    results["with_weather"] = {
        "n_feat": 188 + n_w,
        "auc": round(float(roc_auc_score(yte, p1)), 4),
        "ap": round(float(average_precision_score(yte, p1)), 4),
        "precision": round(float(precision_score(yte, pr1, zero_division=0)), 4),
        "recall": round(float(recall_score(yte, pr1, zero_division=0)), 4),
    }
    print("with_weather:", results["with_weather"])
    results["delta_auc"] = round(results["with_weather"]["auc"] - results["baseline"]["auc"], 4)
    results["delta_ap"] = round(results["with_weather"]["ap"] - results["baseline"]["ap"], 4)

    # save headline NOW (persist even if the slower importance step is cut short)
    Path("/home/junai/lct/ml-data/weather/weather-model-results.json").write_text(
        json.dumps({
            "single_weather_var_auc_2026": single_mag,
            "daily_corr": tbl.to_dict("records"),
            **results,
        }, indent=2, ensure_ascii=False))

    # (d) permutation importance of ONLY the 16 weather cols on a test subset
    print("\n== permutation importance of weather cols (subset) ==")
    try:
        n = 20000
        Xs = Xte_w[:n].copy()
        ys = yte[:n]
        base_auc = roc_auc_score(ys, m1.predict_proba(Xs)[:, 1])
        nreps = 3
        rng = np.random.default_rng(42)
        off = N_FEAT  # wx cols are the last n_w in Xte_w
        wx_imp = {}
        for k, c in enumerate(wx_cols):
            col = Xs[:, off + k].copy()
            gains = []
            for _ in range(nreps):
                Xs[:, off + k] = rng.permutation(col)
                a = roc_auc_score(ys, m1.predict_proba(Xs)[:, 1])
                gains.append(base_auc - a)
            Xs[:, off + k] = col  # restore
            wx_imp[c] = round(float(np.mean(gains)), 5)
        w_sum = sum(wx_imp.values())
        results["weather_perm_importance"] = wx_imp
        results["weather_perm_importance_sum"] = round(w_sum, 5)
        results["subset_base_auc"] = round(float(base_auc), 4)
        print(f"subset base AUC (n={n}): {base_auc:.4f}")
        print("per-var wx perm importance (AUC drop when shuffled):")
        for c in sorted(wx_imp, key=wx_imp.get, reverse=True):
            print(f"  {c:28s} {wx_imp[c]:+.5f}")
        print(f"SUM weather perm-importance: {w_sum:+.5f}")
    except Exception as e:
        print("importance step failed (headline already saved):", type(e).__name__, e)

    # final save (with importance if it succeeded)
    Path("/home/junai/lct/ml-data/weather/weather-model-results.json").write_text(
        json.dumps({
            "single_weather_var_auc_2026": single_mag,
            "daily_corr": tbl.to_dict("records"),
            **results,
        }, indent=2, ensure_ascii=False))
    print("\nDONE. results -> /home/junai/lct/ml-data/weather/weather-model-results.json")


if __name__ == "__main__":
    main()
