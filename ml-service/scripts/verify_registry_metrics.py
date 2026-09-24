"""Verify registry recall/precision/AUC by independent recomputation.

For each category: stream_split the features, load the SAVED model.lgb, predict
on the sealed 2026 test split, compute AUC + precision/recall at the model's
saved threshold (None -> 0.5), and compare against meta.json. Sequential + gc to
stay under the 3GB box.
"""
import gc
import json
import sys

sys.path.insert(0, ".")
import numpy as np
import lightgbm as lgb
from app.models.lgbm_model import stream_split, predict_proba
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, f1_score
from pathlib import Path

FEAT = Path("/home/junai/lct/ml-data/features")
MODELS = Path("/home/junai/lct/ml-service/models")
CATS = ["fire-risk", "unauthorized-access", "infrastructure-wear", "sensor-failure"]


def main():
    for c in CATS:
        f = FEAT / f"features-{c}.parquet"
        meta = json.loads((MODELS / c / "meta.json").read_text())
        thr = meta.get("threshold")
        thr_eff = thr if thr is not None else 0.5
        ds = stream_split(
            str(f), train_max_year=2026, valid_year=2025, test_year=2026,
            max_train_rows=10**9, max_valid_rows=10**9,
        )
        b = lgb.Booster(model_file=str(MODELS / c / "model.lgb"))
        p = predict_proba(b, ds["Xte"])
        y = ds["yte"].astype(int)
        auc = float(roc_auc_score(y, p))
        ap = float(average_precision_score(y, p))
        pr = (p >= thr_eff).astype(int)
        prec = float(precision_score(y, pr, zero_division=0))
        rec = float(recall_score(y, pr, zero_division=0))
        f1 = float(f1_score(y, pr, zero_division=0))
        m = meta["metrics"]
        print(
            f"{c:22s} thr={thr}  "
            f"TEST auc={auc:.4f} ap={ap:.4f} prec={prec:.4f} rec={rec:.4f} f1={f1:.4f}  n={len(y)}",
            flush=True,
        )
        print(
            f"{'':22s}  META  auc={m.get('auc')} ap={m.get('ap')} prec={m.get('precision')} rec={m.get('recall')} f1={m.get('f1')}",
            flush=True,
        )
        del ds, b, p, y, pr
        gc.collect()


if __name__ == "__main__":
    main()
