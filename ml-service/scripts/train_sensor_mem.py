"""One-off: train sensor-failure (1.25M rows) under a 1.7GB memory ceiling.

scripts.train would hold ALL split arrays + the lgb Dataset + booster in one
process (~2GB) and OOM. Instead:

  phase=splits  -> stream_split once, persist X/y/names to npz, exit.
  phase=phase1  -> load tr+va only (~1.0GB), early stopping on valid=2025,
                   save booster -> models/sensor-failure/phase1.booster, exit.
  phase=phase2  -> load tr+te only (~0.9GB), fixed final_rounds (from phase1),
                   save to registry exactly like train_lgbm does, exit.

The workflow matches scripts/train.py train_lgbm: lgbm engine, 11 lags, no
tuned params, sensor-failure is NOT in THRESHOLD_CATEGORIES (threshold 0.5),
train<2026, valid=2025, test=2026.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.lgbm_model import (  # noqa: E402
    LGB_PARAMS_DEFAULT,
    engine_tag,
    fit_lgbm,
    metrics,
    predict_proba,
    stream_split,
)
from app.models.registry import get_registry  # noqa: E402

FEAT_DIR = Path("/home/junai/lct/ml-data/features")
SP = FEAT_DIR / "sensor-split.npz"
MODELS = Path(__file__).resolve().parents[1] / "models" / "sensor-failure"
P1 = MODELS / "phase1.booster"


def _save_splits(names, ds):
    np.savez(
        SP,
        names=np.array(names),
        Xtr=ds["Xtr"], ytr=ds["ytr"],
        Xva=ds["Xva"], yva=ds["yva"],
        Xte=ds["Xte"], yte=ds["yte"],
    )
    print(f"SPLITS SAVED {SP} n={ds['n']:,}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["splits", "phase1", "phase2"])
    a = p.parse_args()

    if a.phase == "splits":
        ds = stream_split(str(FEAT_DIR / "features-sensor-failure.parquet"),
                          train_max_year=2026, valid_year=2025, test_year=2026)
        _save_splits(ds["names"], ds)
        return

    z = np.load(SP)
    names = [str(x) for x in z["names"]]
    n = len(names)

    if a.phase == "phase1":
        del z
        Xtr, ytr = np.load(SP)["Xtr"], np.load(SP)["ytr"]
        Xva, yva = np.load(SP)["Xva"], np.load(SP)["yva"]
        train_data = lgb.Dataset(Xtr, label=ytr)
        valid_data = lgb.Dataset(Xva, label=yva, reference=train_data)
        booster = fit_lgbm(train_data, params=dict(LGB_PARAMS_DEFAULT),
                           rounds=300, valid=valid_data, early_stopping=50)
        final_rounds = int(booster.best_iteration or 300)
        booster.save_model(str(P1))
        (MODELS / "phase1.json").write_text(json.dumps({"final_rounds": final_rounds}))
        print(f"PHASE1 OK final_rounds={final_rounds}", flush=True)
        return

    # phase2: tr + te only
    del z
    Xtr, ytr = np.load(SP)["Xtr"], np.load(SP)["ytr"]
    Xte, yte = np.load(SP)["Xte"], np.load(SP)["yte"]
    final_rounds = json.loads((MODELS / "phase1.json").read_text())["final_rounds"]
    booster = fit_lgbm(lgb.Dataset(Xtr, label=ytr),
                       params=dict(LGB_PARAMS_DEFAULT), rounds=final_rounds)
    proba = predict_proba(booster, Xte)
    m = metrics(yte, proba, threshold=0.5)
    m.update({
        "engine": engine_tag(),
        "source": f"real ({FEAT_DIR.name})",
        "split": f"train<2026={Xtr.shape[0]:,}, valid=2025, test=2026={Xte.shape[0]:,}",
        "best_iteration": None,
        "final_rounds": final_rounds,
        "n_features": n,
        "lags": True,
        "tuned": False,
        "test_positive_rate": round(float(yte.mean()), 4),
    })
    get_registry().save("sensor-failure", booster, names, m,
                        engine=engine_tag(), threshold=None)
    print(f"PHASE2 OK final_rounds={final_rounds} "
          f"auc={m['auc']} ap={m['ap']} precision={m['precision']} recall={m['recall']}",
          flush=True)


if __name__ == "__main__":
    main()
