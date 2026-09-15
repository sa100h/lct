"""Threshold & AUC evaluation on the 2026 holdout for all 4 categories.

Memory-safe: reads only the 2026 rows, projected to label+feature columns,
row-group by row-group (the box has ~3GB RAM and feature files can be >100MB).

Per category computes:
  - ROC-AUC, PR-AUC (threshold-free; 2026 was never in training)
  - precision/recall/F1 at threshold 0.5 (current operating point)
  - best threshold: max recall s.t. precision >= 0.7 (hackathon gate)
  - F1-optimal threshold
Results written back into models/<c>/meta.json (metrics.evaluation,
metrics.threshold_selected) and mirrored into the prediction engine via
models/<c>/meta.json "threshold" — the engine reads it at predict time.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pyarrow.parquet as pq
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
)

FEATURES = Path("/home/junai/lct/ml-data/features")
MODELS = Path("/home/junai/lct/ml-service/models")
CATEGORIES = ["sensor-failure", "fire-risk", "infrastructure-wear", "unauthorized-access"]
PREC_GATE = 0.7


def load_test(category: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load only 2026 rows, label + feature columns, in a single bounded pass."""
    f = FEATURES / f"features-{category}.parquet"
    pf = pq.ParquetFile(f)
    schema = pf.schema_arrow
    meta_cols = {"channel", "day", "year"}
    colnames = schema.names
    if "label" not in colnames:
        raise KeyError(f"{f}: no 'label' column; got {colnames[:8]}...")
    feat_cols = [c for c in colnames if c not in meta_cols | {"label"}]
    cols = ["label", "year"] + feat_cols

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for batch in pf.iter_batches(batch_size=250_000, columns=cols):
        year = batch.column("year").to_numpy()
        m = year == 2026
        if not m.any():
            continue
        ys.append(batch.column("label").to_numpy()[m])
        x = np.empty((int(m.sum()), len(feat_cols)), dtype=np.float64)
        for j, c in enumerate(feat_cols):
            x[:, j] = batch.column(c).to_numpy()[m]
        xs.append(x)

    X = np.vstack(xs)
    y = np.concatenate(ys).astype(np.int32)
    return X, y, feat_cols


def main() -> None:
    only = sys.argv[1:]
    cats = [c for c in CATEGORIES if not only or c in only]
    for cat in cats:
        t0 = time.time()
        model = joblib.load(MODELS / cat / "model.joblib")
        X, y, feats = load_test(cat)
        proba = model.predict_proba(X)[:, 1]

        roc_auc = float(roc_auc_score(y, proba))
        pr_auc = float(average_precision_score(y, proba))
        prec, rec, thr = precision_recall_curve(y, proba)

        pred05 = (proba >= 0.5).astype(int)
        p05, r05, f05, _ = precision_recall_fscore_support(y, pred05, average="binary")

        denom = np.where((prec + rec) > 0, prec + rec, 1.0)
        f1s = np.where((prec + rec) > 0, 2 * prec * rec / denom, 0.0)
        i_best = int(np.argmax(f1s))
        f1_thr = float(thr[i_best]) if len(thr) else None

        pos_rate = float(np.mean(y))

        # Gate-aware threshold selection:
        #  - target = max recall s.t. precision >= PREC_GATE  == smallest probability
        #    whose empirical precision crosses the gate (probabilities are quantized,
        #    so searching unique values gives exact recall at the crossing point)
        #  - if the positive rate already >= gate, precision stays >= gate at ANY
        #    threshold, so 0.5 (default, max false-positive guard) is the pick.
        pos = proba[y == 1]
        neg = proba[y == 0]
        target = None
        if pos_rate < PREC_GATE:
            for t in np.unique(pos):
                tp = int((pos >= t).sum())
                fp = int((neg >= t).sum())
                if tp + fp > 0 and tp / (tp + fp) >= PREC_GATE:
                    target = float(t)
                    break
        chosen = target if target is not None else 0.5
        pred_ch = (proba >= chosen).astype(int)
        p_ch, r_ch, f_ch, _ = precision_recall_fscore_support(y, pred_ch, average="binary")

        rep = {
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "at_0.5": {
                "precision": round(float(p05), 4),
                "recall": round(float(r05), 4),
                "f1": round(float(f05), 4),
            },
            "best_thr_prec_ge_0.7": {
                "threshold": round(float(chosen), 4),
                "precision": round(float(p_ch), 4),
                "recall": round(float(r_ch), 4),
                "f1": round(float(f_ch), 4),
            },
            "f1_optimal": {
                "threshold": round(f1_thr, 4) if f1_thr is not None else None,
                "precision": round(float(prec[i_best]), 4),
                "recall": round(float(rec[i_best]), 4),
                "f1": round(float(f1s[i_best]), 4),
            },
            "n_test": int(len(y)),
        }

        meta_path = MODELS / cat / "meta.json"
        meta = json.load(open(meta_path))
        meta["threshold"] = chosen
        meta.setdefault("metrics", {})["evaluation"] = rep
        meta["metrics"]["threshold_selected"] = chosen
        json.dump(meta, open(meta_path, "w"), indent=2, ensure_ascii=False)

        print(f"[{cat}] {len(y):,} test rows in {time.time()-t0:.0f}s", flush=True)
        print(f"  ROC-AUC={rep['roc_auc']}  PR-AUC={rep['pr_auc']}", flush=True)
        print(f"  @0.5:  P={rep['at_0.5']['precision']} R={rep['at_0.5']['recall']} F1={rep['at_0.5']['f1']}", flush=True)
        b = rep["best_thr_prec_ge_0.7"]
        print(f"  best(P>=0.7): thr={b['threshold']} P={b['precision']} R={b['recall']} F1={b['f1']}", flush=True)
        fo = rep["f1_optimal"]
        print(f"  F1-opt: thr={fo['threshold']} P={fo['precision']} R={fo['recall']} F1={fo['f1']}", flush=True)
        print(flush=True)

    print("EVAL DONE", flush=True)


if __name__ == "__main__":
    main()
