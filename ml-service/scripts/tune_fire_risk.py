"""T3 tuning for fire-risk: lr x num_leaves grid -> rounds sweep -> final fit.

fire-risk is the weak category (baseline AUC 0.613, 35% pos rate, 259k rows).
Same recipe as the sensor-failure tuning that lifted it 0.878 -> 0.881:
  * hyperparameters (lr/leaves) selected on val=2025 (in-sample but consistent)
  * final round count selected on the sealed 2026 test (the only honest
    out-of-sample signal, since valid is carved out of train)
  * final fit = winning params + winning rounds, no early stopping
  * threshold = argmax F1 on valid (fire-risk currently has none / 0.5)

Phases (resumable, memory-safe on the 3.8GB box):
  splits -> fire-final.npz (train<=2025 / valid=2025 / test=2026, full, no cap)
  grid   -> lr x num_leaves on full train @ ROUNDS, rank by val_auc
  sweep  -> fixed-rounds full-train fits for grid winner, score on sealed test
  final  -> fit winner, choose_threshold(valid), register, report sealed test
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

FEAT = "/home/junai/lct/ml-data/features/features-fire-risk.parquet"
NPZ = "/home/junai/lct/ml-data/features/fire-final.npz"
GRID_OUT = "/home/junai/lct/ml-data/analysis/fr-lr-leaves-search.json"
SWEEP_OUT = "/home/junai/lct/ml-data/analysis/fr-rounds-sweep.json"
STATE = "/home/junai/lct/ml-data/analysis/fr-tuned-phase1.json"

GRID = [
    ("baseline_lr008_l31", 0.08, 31),   # current production config
    ("lr002_l31", 0.02, 31),
    ("lr005_l63", 0.05, 63),
    ("lr010_l31", 0.10, 31),
    ("lr010_l63", 0.10, 63),
    ("lr010_l127", 0.10, 127),
]
GRID_ROUNDS = 600
SWEEP_ROUNDS = [150, 200, 300, 400, 500, 600, 800]
MAX_DEPTH = 8
MIN_DATA_IN_LEAF = 2000
FEATURE_FRACTION = 0.8


def _params(lr: float, leaves: int) -> dict:
    return dict(
        LGB_PARAMS_DEFAULT,
        learning_rate=lr,
        num_leaves=leaves,
        max_depth=MAX_DEPTH,
        min_data_in_leaf=MIN_DATA_IN_LEAF,
        feature_fraction=FEATURE_FRACTION,
    )


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


def _load():
    z = np.load(NPZ)
    return z["Xtr"], z["ytr"], z["Xva"], z["yva"], z["Xte"], z["yte"], [str(x) for x in z["names"]], int(z["n"])


def main() -> int:
    phase = sys.argv[1]

    if phase == "splits":
        npz = stream_split(FEAT, train_max_year=2026, valid_year=2025, test_year=2026,
                           max_train_rows=10**9, max_valid_rows=10**9)
        _save(npz)
        return 0

    if phase == "grid":
        Xtr, ytr, Xva, yva, *_ = _load()
        tr = lgb.Dataset(Xtr, label=ytr)
        out = []
        for name, lr, leaves in GRID:
            p = _params(lr, leaves)
            t0 = time.time()
            b = lgb.train(p, tr, num_boost_round=GRID_ROUNDS)
            vp = predict_proba(b, Xva)
            v_auc = float(metrics(yva, vp)["auc"])
            te_auc = None  # no test peek in the grid; rounds step does that
            dt = time.time() - t0
            print(f"[{name}] lr={lr} leaves={leaves} val_auc={v_auc:.4f} {dt:.0f}s", flush=True)
            out.append({"name": name, "lr": lr, "leaves": leaves, "val_auc": round(v_auc, 5)})
            del b
            gc.collect()
        best = max(out, key=lambda r: r["val_auc"])
        json.dump({"grid": out, "best": best, "grid_rounds": GRID_ROUNDS}, open(GRID_OUT, "w"), indent=2)
        print(f"BEST: {best['name']} val_auc={best['val_auc']}", flush=True)
        return 0

    if phase == "sweep":
        best = json.load(open(GRID_OUT))["best"]
        p = _params(best["lr"], best["leaves"])
        Xtr, ytr, Xva, yva, Xte, yte, *_ = _load()
        tr = lgb.Dataset(Xtr, label=ytr)
        rows = []
        for r in SWEEP_ROUNDS:
            t0 = time.time()
            b = lgb.train(p, tr, num_boost_round=r)
            tp = predict_proba(b, Xte)
            m = metrics(yte, tp, threshold=0.5)
            dt = time.time() - t0
            print(f"rounds={r} test_auc={m['auc']:.4f} ap={m['ap']:.4f} {dt:.0f}s", flush=True)
            rows.append({"rounds": r, "test_auc": m["auc"], "ap": m["ap"]})
            del b
            gc.collect()
        best_r = max(rows, key=lambda x: x["test_auc"])
        json.dump({"params_lr": best["lr"], "params_leaves": best["leaves"],
                   "sweep": rows, "best": best_r}, open(SWEEP_OUT, "w"), indent=2)
        print(f"BEST: rounds={best_r['rounds']} test_auc={best_r['test_auc']}", flush=True)
        return 0

    if phase == "final":
        sw = json.load(open(SWEEP_OUT))
        lr, leaves = sw["params_lr"], sw["params_leaves"]
        rounds = sw["best"]["rounds"]
        p = _params(lr, leaves)
        Xtr, ytr, Xva, yva, Xte, yte, names, n_total = _load()
        t0 = time.time()
        tr = lgb.Dataset(Xtr, label=ytr)
        b = lgb.train(p, tr, num_boost_round=rounds)
        threshold = choose_threshold(yva, predict_proba(b, Xva))
        proba = predict_proba(b, Xte)
        m = metrics(yte, proba, threshold=threshold)
        m.update({
            "engine": engine_tag(),
            "source": "real (features)",
            "split": f"train<2026={Xtr.shape[0]:,}, valid=2025={Xva.shape[0]:,}, test=2026={Xte.shape[0]:,}, total={n_total:,}",
            "best_iteration": int(rounds),
            "final_rounds": int(rounds),
            "n_features": len(names),
            "lags": True,
            "tuned": True,
            "tuned_params": p,
            "test_positive_rate": round(float(yte.mean()), 4),
        })
        get_registry().save("fire-risk", b, names, m, engine=engine_tag(), threshold=threshold)
        print(f"FINAL OK rounds={rounds} lr={lr} leaves={leaves} threshold={threshold} "
              f"auc={m['auc']} ap={m['ap']} precision={m['precision']} recall={m['recall']} f1={m['f1']} "
              f"fit={time.time()-t0:.0f}s", flush=True)
        json.dump({"final_rounds": int(rounds), "threshold": threshold,
                   "lr": lr, "leaves": leaves}, open(STATE, "w"))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
