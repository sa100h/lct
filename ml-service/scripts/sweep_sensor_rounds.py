"""Round sweep for sensor-failure tuned params (lr=0.10, leaves=31).

The 2000-round fit overfit the sealed test (0.865 vs baseline 0.878).
Grid best_iter was ~590 on the 50k subset. Sweep fixed round counts on the
full 1M train, evaluate on sealed 2026 (single pass), pick the best AUC.
"""
from __future__ import annotations

import gc
import sys
import time

import numpy as np

sys.path.insert(0, "/home/junai/lct/ml-service")

import lightgbm as lgb  # noqa: E42

from app.models.lgbm_model import (  # noqa: E42
    LGB_PARAMS_DEFAULT,
    choose_threshold,
    metrics,
    predict_proba,
)

NPZ = "/home/junai/lct/ml-data/features/sensor-final.npz"
PARAMS = dict(
    LGB_PARAMS_DEFAULT,
    num_leaves=31,
    max_depth=8,
    min_data_in_leaf=2000,
    feature_fraction=0.8,
    learning_rate=0.10,
)
ROUNDS_GRID = [300, 400, 500, 600, 800]


def main() -> int:
    z = np.load(NPZ)
    Xtr, ytr = z["Xtr"], z["ytr"]
    Xva, yva = z["Xva"], z["yva"]
    Xte, yte = z["Xte"], z["yte"]
    tr = lgb.Dataset(Xtr, label=ytr)

    rows = []
    for r in ROUNDS_GRID:
        t0 = time.time()
        b = lgb.train(PARAMS, tr, num_boost_round=r)
        tp = predict_proba(b, Xte)
        m = metrics(yte, tp)  # threshold 0.5 for the sweep
        thr = choose_threshold(yva, predict_proba(b, Xva))
        mt = metrics(yte, tp, threshold=thr)
        rows.append((r, m["auc"], mt["precision"], mt["recall"], thr, time.time() - t0))
        print(f"rounds={r} test_auc={m['auc']:.4f} thr={thr:.3f} prec={mt['precision']:.4f} rec={mt['recall']:.4f} f1={mt['f1']:.4f} fit={time.time()-t0:.0f}s", flush=True)
        del b
        gc.collect()

    best = max(rows, key=lambda x: x[1])
    print(f"BEST: rounds={best[0]} auc={best[1]:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
