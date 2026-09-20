#!/usr/bin/env python3
"""Plan T3: train the tuned LightGBM per category with the plan's best
params (1500 rounds cap, early stop 100, num_leaves 63, max_depth 8,
min_data_in_leaf 2000, feature_fraction 0.8, lr 0.05) on real data.

Split (lgbm_model.stream_split, 3GB box):
  train  = years <= 2025 (cap 500k rows)   valid = 2025 (cap 200k)  test = 2026

Writes ml-data/lags/lgbm-tuned-results.json in the shape scripts/train.py
consumes:  {"per_category": {cat: {"params": {...}, "best_iteration": N}}}

It does NOT touch the live registry — the final production fit is
`.venv/bin/python -m scripts.train --tuned` (plan T6).
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/junai/lct/ml-service")

import lightgbm as lgb  # noqa: E402

from app.models.lgbm_model import (  # noqa: E402
    FEAT_DIR,
    LGB_PARAMS_DEFAULT,
    metrics,
    predict_proba,
    stream_split,
)
from app.models.registry import CATEGORIES  # noqa: E402

# plan T3 tuned params (validated in research on per-category held-out years)
TUNED = dict(
    LGB_PARAMS_DEFAULT,
    num_leaves=63,
    max_depth=8,
    min_data_in_leaf=2000,
    feature_fraction=0.8,
    learning_rate=0.05,
)
NUM_BOOST_ROUND = 1500
EARLY_STOP = 100


def main() -> int:
    results: dict[str, dict] = {}
    for cat in CATEGORIES:
        fname = f"features-{cat}.parquet"
        t0 = time.time()
        ds = stream_split(
            str(FEAT_DIR / fname),
            train_max_year=2026,
            valid_year=2025,
            test_year=2026,
            max_train_rows=500_000,
            max_valid_rows=200_000,
        )
        tr = lgb.Dataset(ds["Xtr"], label=ds["ytr"])
        va = lgb.Dataset(ds["Xva"], label=ds["yva"], reference=tr)
        booster = lgb.train(
            TUNED,
            tr,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[va],
            valid_names=["valid"],
            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)],
        )
        fit_s = time.time() - t0
        m = metrics(ds["yte"], predict_proba(booster, ds["Xte"]))
        ok = m["auc"] >= 0.75 and m["ap"] >= 0.50
        results[cat] = {
            **m,
            "best_iteration": int(booster.best_iteration),
            "fit_sec": round(fit_s, 1),
            "plan_threshold_met": ok,
        }
        print(
            f"[{cat}] {fit_s:.0f}s  best_iter={booster.best_iteration}  {m}  "
            f"plan 0.75/0.50={'PASS' if ok else 'FAIL'}",
            flush=True,
        )
        del ds, tr, va, booster

    out = {
        "tuned_params": TUNED,
        "num_boost_round": NUM_BOOST_ROUND,
        "early_stop": EARLY_STOP,
        "results": results,
        # shape consumed by scripts/train.py _tuned_params()
        "per_category": {
            cat: {
                "params": {
                    k: TUNED[k]
                    for k in (
                        "num_leaves",
                        "max_depth",
                        "min_data_in_leaf",
                        "feature_fraction",
                        "learning_rate",
                    )
                    if k in TUNED
                },
                "rounds": results[cat]["best_iteration"],
                "best_iteration": results[cat]["best_iteration"],
            }
            for cat in results
        },
    }
    path = "/home/junai/lct/ml-data/lags/lgbm-tuned-results.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"-> {path}")
    return 0 if all(r["plan_threshold_met"] for r in results.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
