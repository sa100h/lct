"""T3 hyperparameter search for sensor-failure: lr x num_leaves grid.

Selection set: 50k seeded rows (train, years<=2025) + 150k rows (valid, 2025)
from features-sensor-failure.parquet.  Full 1.25M-row production fit happens
separately after the winner is known.
"""
from __future__ import annotations

import json
import sys
import time

import lightgbm as lgb
import numpy as np

sys.path.insert(0, "/home/junai/lct/ml-service")

from app.models.lgbm_model import (  # noqa: E402
    FEAT_DIR,
    LGB_PARAMS_DEFAULT,
    metrics,
    predict_proba,
    stream_split,
)

FEAT = str(FEAT_DIR / "features-sensor-failure.parquet")
GRID = [
    # (name, lr, num_leaves) — baseline = plan T3 fixed params
    ("lr002_l31", 0.02, 31),
    ("lr002_l127", 0.02, 127),
    ("lr05_l63", 0.05, 63),
    ("lr10_l31", 0.10, 31),
    ("lr10_l127", 0.10, 127),
]
ROUNDS = 600
PATIENCE = 50
MAX_TRAIN = 50_000
MAX_VALID = 150_000


def main() -> int:
    t0 = time.time()
    ds = stream_split(
        FEAT,
        train_max_year=2026,
        valid_year=2025,
        test_year=2026,
        max_train_rows=MAX_TRAIN,
        max_valid_rows=MAX_VALID,
    )
    print(f"split: train={ds['Xtr'].shape[0]} valid={ds['Xva'].shape[0]} test={ds['Xte'].shape[0]}", flush=True)
    tr = lgb.Dataset(ds["Xtr"], label=ds["ytr"])
    va = lgb.Dataset(ds["Xva"], label=ds["yva"], reference=tr)
    out = []
    for name, lr, leaves in GRID:
        params = dict(
            LGB_PARAMS_DEFAULT,
            num_leaves=leaves,
            max_depth=8,
            min_data_in_leaf=2000,
            feature_fraction=0.8,
            learning_rate=lr,
        )
        t1 = time.time()
        b = lgb.train(
            params,
            tr,
            num_boost_round=ROUNDS,
            valid_sets=[va],
            valid_names=["valid"],
            callbacks=[lgb.early_stopping(PATIENCE, verbose=False, first_metric_only=True)],
        )
        vp = predict_proba(b, ds["Xva"])
        v_auc = float(_auc(ds["yva"], vp))
        best_iter = int(b.best_iteration)
        print(f"[{name}] lr={lr} leaves={leaves} best_iter={best_iter} val_auc={v_auc:.4f} {time.time()-t1:.0f}s", flush=True)
        out.append({"name": name, "lr": lr, "leaves": leaves, "best_iteration": best_iter, "val_auc": round(v_auc, 5)})
    best = max(out, key=lambda r: r["val_auc"])
    print(f"BEST: {best['name']} val_auc={best['val_auc']} best_iter={best['best_iteration']}", flush=True)
    print(f"total {time.time()-t0:.0f}s", flush=True)
    with open("/home/junai/lct/ml-data/analysis/sf-lr-leaves-search.json", "w") as f:
        json.dump({"grid": out, "best": best, "max_rounds": ROUNDS, "patience": PATIENCE}, f, indent=2)
    print("-> ml-data/analysis/sf-lr-leaves-search.json", flush=True)
    return 0


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    """Mann-Whitney AUC via ranks (no sklearn needed)."""
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1, dtype=np.float64)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    r1 = ranks[y.astype(bool)]
    return float((r1.sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


if __name__ == "__main__":
    sys.exit(main())
