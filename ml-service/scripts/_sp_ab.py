"""A/B: baseline (lags, current production recipe) vs baseline+spatial.

Usage:
    .venv/bin/python scripts/_sp_ab.py baseline   # 4 categories, no spatial
    .venv/bin/python scripts/_sp_ab.py spatial    # 4 categories, +10 spatial cols

Same recipe as scripts/train.py: train<2026 (subsamp 1M), valid=2025 early stop,
test=2026 final fit, sealed test opened once. Does NOT touch the registry.
Results appended to /home/junai/lct/ml-data/lags/spatial-ab-results.json.
"""
import json
import os
import sys
import time

import lightgbm as lgb

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.main import Category
from app.models.lgbm_model import (
    LGB_PARAMS_DEFAULT,
    choose_threshold,
    fit_lgbm,
    metrics,
    predict_proba,
    stream_split,
)

FEAT_DIR = "/home/junai/lct/ml-data/features/"
SPATIAL = FEAT_DIR + "spatial.parquet"
OUT = "/home/junai/lct/ml-data/lags/spatial-ab-results.json"
THRESHOLD_CATEGORIES = {"sensor-failure", "unauthorized-access"}


def run(arm: str) -> None:
    with_spatial = arm == "spatial"
    t0 = time.time()
    results = {}
    for cat in [c.value for c in Category]:
        t1 = time.time()
        ds = stream_split(FEAT_DIR + f"features-{cat}.parquet",
                          train_max_year=2026, valid_year=2025, test_year=2026,
                          spatial_path=SPATIAL if with_spatial else None)
        params = dict(LGB_PARAMS_DEFAULT)
        train_data = lgb.Dataset(ds["Xtr"], label=ds["ytr"])
        valid_data = lgb.Dataset(ds["Xva"], label=ds["yva"], reference=train_data)
        booster = fit_lgbm(train_data, params=params, rounds=300,
                           valid=valid_data, early_stopping=50)
        final_rounds = booster.best_iteration or 300
        threshold = None
        if cat in THRESHOLD_CATEGORIES:
            threshold = choose_threshold(ds["yva"], predict_proba(booster, ds["Xva"]))
        booster = fit_lgbm(train_data, params=params, rounds=final_rounds)
        proba = predict_proba(booster, ds["Xte"])
        m = metrics(ds["yte"], proba, threshold=threshold if threshold is not None else 0.5)
        m.update(arm=arm, spatial=with_spatial, n_features=len(ds["names"]),
                 final_rounds=final_rounds, threshold=threshold,
                 secs=round(time.time() - t1, 1))
        results[cat] = m
        print(f"[{arm}] {cat}: auc={m['auc']} ap={m['ap']} p={m['precision']} "
              f"r={m['recall']} f1={m['f1']} rounds={final_rounds} "
              f"thr={threshold} {m['secs']}s", flush=True)
        # cache incrementally so a later failure loses nothing (merge, don't clobber)
        existing = {}
        if os.path.exists(OUT):
            with open(OUT) as f:
                existing = json.load(f)
        existing[arm] = results
        with open(OUT, "w") as f:
            json.dump(existing, f, indent=1)
        # feature importance for the spatial arm (which spatial cols matter)
        if with_spatial:
            imp = booster.feature_importance("gain")
            names = ds["names"]
            sp = sorted(zip(names[len(names)-10:], imp[len(names)-10:]),
                        key=lambda x: -x[1])
            print(f"[{arm}] {cat} spatial gains:",
                  {k: int(v) for k, v in sp[:4]}, flush=True)
    print(f"ARM {arm} DONE in {round(time.time()-t0)}s", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
