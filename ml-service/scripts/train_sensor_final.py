"""sensor-failure production fit with tuned params (lr=0.10, leaves=31).

Memory-safe 3 phases (same recipe as train_sensor_mem.py; 3GB box):
  splits -> sensor-final.npz (train<=2025 cap 1M / valid 2025 / test 2026)
  p1     -> early stopping (2000 rounds, patience 100) on full train vs valid,
            save best_iteration + threshold = choose_threshold(valid proba)
  p2     -> final fit with best_iteration, metrics on sealed 2026, save registry

Tuned params (scripts/tune_sensor_search.py, ml-data/analysis/sf-lr-leaves-search.json):
  lr=0.10, num_leaves=31, max_depth=8, min_data_in_leaf=2000, feature_fraction=0.8
  (vs LGB_PARAMS_DEFAULT lr=0.08, no max_depth, min_data_in_leaf=20, ff=0.9)
"""
from __future__ import annotations

import gc
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/home/junai/lct/ml-service")

import lightgbm as lgb  # noqa: E402

from app.models.lgbm_model import (  # noqa: E402
    LGB_PARAMS_DEFAULT,
    choose_threshold,
    engine_tag,
    metrics,
    predict_proba,
    stream_split,
)
from app.models.registry import get_registry  # noqa: E402

FEAT = "/home/junai/lct/ml-data/features/features-sensor-failure.parquet"
NPZ = "/home/junai/lct/ml-data/features/sensor-final.npz"
STATE = "/home/junai/lct/ml-data/analysis/sf-tuned-phase1.json"
PARAMS = dict(
    LGB_PARAMS_DEFAULT,
    num_leaves=31,
    max_depth=8,
    min_data_in_leaf=2000,
    feature_fraction=0.8,
    learning_rate=0.10,
)
ROUNDS = 2000
PATIENCE = 100


def _save(npz) -> None:
    np.savez_compressed(
        NPZ,
        names=npz["names"],
        Xtr=npz["Xtr"], ytr=npz["ytr"],
        Xva=npz["Xva"], yva=npz["yva"],
        Xte=npz["Xte"], yte=npz["yte"],
        n=npz["n"],
    )
    print(f"SAVED {NPZ} tr={npz['Xtr'].shape} va={npz['Xva'].shape} te={npz['Xte'].shape} feats={len(npz['names'])}", flush=True)


def main() -> int:
    phase = sys.argv[1]
    if phase == "splits":
        npz = stream_split(FEAT, train_max_year=2026, valid_year=2025, test_year=2026)
        _save(npz)
        return 0

    if phase == "p1":
        z = np.load(NPZ)
        Xtr, ytr = z["Xtr"], z["ytr"]
        Xva, yva = z["Xva"], z["yva"]
        tr = lgb.Dataset(Xtr, label=ytr)
        va = lgb.Dataset(Xva, label=yva, reference=tr)
        t0 = time.time()
        b = lgb.train(
            PARAMS, tr, num_boost_round=ROUNDS,
            valid_sets=[va], valid_names=["valid"],
            callbacks=[lgb.early_stopping(PATIENCE, verbose=False, first_metric_only=True)],
        )
        valid_proba = predict_proba(b, Xva)
        threshold = choose_threshold(yva, valid_proba)
        val_auc = float(metrics(yva, valid_proba)["auc"])
        json.dump({"final_rounds": int(b.best_iteration), "threshold": threshold,
                   "val_auc": val_auc, "fit_sec": round(time.time() - t0, 1)},
                  open(STATE, "w"))
        b.save_model("/home/junai/lct/ml-service/models/sensor-failure/tuned-p1.lgb")
        print(f"PHASE1 OK best_iter={b.best_iteration} threshold={threshold} val_auc={val_auc:.4f} fit={time.time()-t0:.0f}s", flush=True)
        del tr, va, b, z
        gc.collect()
        return 0

    if phase == "p2":
        st = json.load(open(STATE))
        rounds = st["final_rounds"]
        threshold = st["threshold"]
        z = np.load(NPZ)
        Xtr, ytr = z["Xtr"], z["ytr"]
        Xte, yte = z["Xte"], z["yte"]
        names = [str(x) for x in z["names"]]
        n_total = int(z["n"])
        t0 = time.time()
        tr = lgb.Dataset(Xtr, label=ytr)
        b = lgb.train(PARAMS, tr, num_boost_round=rounds)
        proba = predict_proba(b, Xte)
        m = metrics(yte, proba, threshold=threshold)
        m.update({
            "engine": engine_tag(),
            "source": "real (features)",
            "split": f"train<2026={Xtr.shape[0]:,}, valid=2025, test=2026={Xte.shape[0]:,}, total={n_total:,}",
            "best_iteration": int(rounds),
            "final_rounds": int(rounds),
            "n_features": len(names),
            "lags": True,
            "tuned": True,
            "tuned_params": PARAMS,
            "test_positive_rate": round(float(yte.mean()), 4),
        })
        get_registry().save("sensor-failure", b, names, m, engine=engine_tag(), threshold=threshold)
        print(f"PHASE2 OK rounds={rounds} threshold={threshold} auc={m['auc']} ap={m['ap']} "
              f"precision={m['precision']} recall={m['recall']} fit={time.time()-t0:.0f}s", flush=True)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
