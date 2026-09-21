"""LightGBM with explicit per-channel temporal (lag) features for LCT — EXPERIMENT.

Now a thin wrapper over the shared production module `app/ingest/lag_features.py`
(the ONE source of lag formulas for train and serve). This script runs the same
experiment that produced `ml-data/lags/lag-model-results.json`:

  Panel: 11,482 channels x day, 2.46M rows, 184 base features + 11 lags.
  Split: train < 2026 (500k sample), test = 2026, seed 42.
  A) LGBM 184 feats   (engine baseline)
  B) LGBM 184 + 11 lags (the temporal model)

Usage:
    python scripts/_lag_model.py            # rerun experiment, write lag-model-results.json
    python scripts/_lag_model.py --check    # rerun, then assert AUC/AP match the saved
                                            # results (lag-formula regression, T1)
Memory-safe: streams 2.46M (channel,day,year,label) once for lags, then streams
features row-group by row-group for the sampled train + test using bool masks.
"""
from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import lightgbm as lgb
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.lag_features import LAG_FEATURES, LAG_SET, compute_lags  # noqa: E402

FEAT = Path("/home/junai/lct/ml-data/features/features-sensor-failure.parquet")
OUT = Path("/home/junai/lct/ml-data/lags/lag-model-results.json")

META = {"channel", "day", "year", "label"}
TEST_YEAR = 2026
MAX_TRAIN = 500_000
SEED = 42

LGB_PARAMS = dict(
    objective="binary",
    n_estimators=300,
    learning_rate=0.08,
    num_leaves=31,
    min_data_in_leaf=20,
    feature_fraction=0.9,
    bagging_fraction=0.9,
    bagging_freq=1,
    is_unbalance=True,
    seed=SEED,
    n_jobs=-1,
    verbose=-1,
)


def build_lags() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Shared-module pass: lags in original row order + (year, label) for masks."""
    ch, d_ord, yr, lab = __import__("app.ingest.lag_features", fromlist=["read_panel_meta"]).read_panel_meta(FEAT)
    return compute_lags(FEAT), yr, lab.astype(np.int8)


def _eval(y, prob) -> dict:
    pred = (prob >= 0.5).astype(int)
    return {
        "auc": round(float(roc_auc_score(y, prob)), 4),
        "ap": round(float(average_precision_score(y, prob)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
    }


def main() -> None:
    check = "--check" in sys.argv
    print("== building per-channel lag features (shared module: app/ingest/lag_features) ==")
    lags, yr, lab = build_lags()
    print(f"panel rows={len(yr):,}")

    tr_mask = yr < TEST_YEAR
    te_mask = yr == TEST_YEAR
    tr_idx = np.flatnonzero(tr_mask)
    te_idx = np.flatnonzero(te_mask)
    rng = np.random.default_rng(SEED)
    keep_ratio = min(1.0, MAX_TRAIN / len(tr_idx))
    tr_pick = np.sort(tr_idx[rng.random(len(tr_idx)) < keep_ratio])
    te_idx = np.sort(te_idx)
    print(f"train sample={len(tr_pick):,}  test={len(te_idx):,}")

    n = len(yr)
    tr_sel = np.zeros(n, dtype=bool); tr_sel[tr_pick] = True
    te_sel = np.zeros(n, dtype=bool); te_sel[te_idx] = True

    pf = pq.ParquetFile(FEAT)
    names = [c for c in pf.schema_arrow.names if c not in META and c not in LAG_SET]
    ncol = len(names)
    tr_X, tr_y, te_X, te_y = [], [], [], []
    offset = 0
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i)
        gn = rg.num_rows
        start, end = offset, offset + gn
        offset = end
        tmask = tr_sel[start:end]
        emask = te_sel[start:end]
        take = tmask | emask
        if not take.any():
            del rg
            continue
        sub = rg.filter(pa.array(take))
        Xc = np.empty((sub.num_rows, ncol), dtype=np.float32)
        for j, nm in enumerate(names):
            Xc[:, j] = sub.column(nm).to_numpy()
        lab_c = sub.column("label").to_numpy()
        tr_X.append(Xc[tmask[take]]); tr_y.append(lab_c[tmask[take]])
        te_X.append(Xc[emask[take]]); te_y.append(lab_c[emask[take]])
        del rg
    Xtr = np.concatenate(tr_X); ytr = np.concatenate(tr_y)
    Xte = np.concatenate(te_X); yte = np.concatenate(te_y)
    del tr_X, tr_y, te_X, te_y
    print(f"Xtr={Xtr.shape}  Xte={Xte.shape}")

    Ltr = np.column_stack([lags[k][tr_pick] for k in LAG_FEATURES]).astype(np.float32)
    Lte = np.column_stack([lags[k][te_idx] for k in LAG_FEATURES]).astype(np.float32)
    print(f"Ltr={Ltr.shape}  Lte={Lte.shape}")

    results = {"n_features_base": int(ncol), "n_lag_features": len(LAG_FEATURES),
               "train_rows": int(len(ytr)), "test_rows": int(len(yte))}

    print("\n[1/2] fitting LGBM base (184 feats)...")
    mb = lgb.LGBMClassifier(**LGB_PARAMS)
    mb.fit(Xtr, ytr)
    results["lgbm_base"] = _eval(yte, mb.predict_proba(Xte)[:, 1])
    print("lgbm_base:", results["lgbm_base"])
    gc.collect()

    print("\n[2/2] fitting LGBM + lags (184+11 feats)...")
    Xtr_w = np.concatenate([Xtr, Ltr], axis=1)
    Xte_w = np.concatenate([Xte, Lte], axis=1)
    del Xtr, Ltr
    gc.collect()
    ml = lgb.LGBMClassifier(**LGB_PARAMS)
    ml.fit(Xtr_w, ytr)
    results["lgbm_lags"] = _eval(yte, ml.predict_proba(Xte_w)[:, 1])
    print("lgbm_lags:", results["lgbm_lags"])
    results["delta_auc"] = round(results["lgbm_lags"]["auc"] - results["lgbm_base"]["auc"], 4)
    results["delta_ap"] = round(results["lgbm_lags"]["ap"] - results["lgbm_base"]["ap"], 4)

    imp = dict(zip(names + LAG_FEATURES, ml.feature_importances_.astype(int)))
    results["lag_gain_importance"] = dict(sorted(((k, int(imp[k])) for k in LAG_FEATURES), key=lambda kv: -kv[1]))
    print("\nlag feature gain importance (LightGBM):")
    for k, v in results["lag_gain_importance"].items():
        print(f"  {k:20s} {v}")
    top10 = sorted(imp.items(), key=lambda kv: -kv[1])[:10]
    print("\ntop-10 overall features:")
    for nm, v in top10:
        tag = "  (LAG)" if nm in LAG_SET else ""
        print(f"  {nm:24s} {v}{tag}")

    if check:
        ref = json.loads(OUT.read_text()) if OUT.exists() else None
        if ref is None:
            print("\n[CHECK] no saved results to compare against; skipping.")
        else:
            ok = True
            for key in ("lgbm_base", "lgbm_lags"):
                for metric in ("auc", "ap", "precision", "recall"):
                    a, b = results[key][metric], ref[key].get(metric)
                    same = a == b
                    ok &= same
                    print(f"[CHECK] {key}.{metric}: rerun={a} saved={b} {'OK' if same else 'MISMATCH'}")
            results["_check_passed"] = bool(ok)
            if not ok:
                print("\n[CHECK] FAILED: rerun diverges from saved lag-model-results.json")
                sys.exit(1)
            print("\n[CHECK] PASSED: shared module reproduces the saved experiment results")

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nDONE. results -> {OUT}")


if __name__ == "__main__":
    main()
