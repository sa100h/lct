"""Leak audit: controlled experiment on the real feature files.

Train on <2026, test on 2026, three feature variants:
  V0 = all features (reproduces the shipped model)
  V1 = minus since_act / since_alar (suspected same-day leak)
  V2 = V1 minus alarm-driven features (a7, a30, ar7, ar30) and the
       category-critical state counts t7_i / t30_i (lagged-label features)

Plus zero-model diagnostics on 2026 only:
  - AUC of the single feature (since_alar == 0)  -> does ONE column carry
    the label?
  - persistence rule: predict 1 if a7 > 0 or any critical t7_i > 0
  - share of 2026 positives with since_alar == 0

No threshold tuning, no look at 2026 beyond the final metrics.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ingest.aggregate import STATES

FEAT = Path("/home/junai/lct/ml-data/features")
VOCAB = json.loads(Path("/home/junai/lct/ml-data/vocab.json").read_text(encoding="utf-8"))
TEST_YEAR = 2026
MAX_TRAIN = 1_000_000

N_STATES = 26


def feat_names(cat: str) -> list[str]:
    f = FEAT / f"features-{cat}.parquet"
    pf = pq.ParquetFile(f)
    return [c for c in pf.schema_arrow.names if c not in {"channel", "day", "year", "label"}]


def load_split(cat: str):
    f = FEAT / f"features-{cat}.parquet"
    pf = pq.ParquetFile(f)
    names = feat_names(cat)
    cols = ["year", "label"] + names
    n_rgs = pf.metadata.num_row_groups

    years = pf.read(columns=["year"]).column(0).to_numpy()
    n = int(years.sum() if False else len(years))
    tr_global = years < TEST_YEAR
    te_global = years == TEST_YEAR
    tr_idx = np.flatnonzero(tr_global)
    rng = np.random.default_rng(42)
    keep_idx = rng.choice(tr_idx, size=min(MAX_TRAIN, len(tr_idx)), replace=False)
    keep = np.zeros(n, dtype=bool)
    keep[keep_idx] = True

    tr_parts, te_parts, tr_y_parts, te_y_parts = [], [], [], []
    pos = 0
    for i in range(n_rgs):
        rg = pf.read_row_group(i, columns=cols)
        sz = rg.num_rows
        sl = slice(pos, pos + sz)
        pos += sz
        yr = rg.column("year").to_numpy()
        lab = rg.column("label").to_numpy().astype(np.int8)
        x = np.column_stack([rg.column(c).to_numpy() for c in names]).astype(np.float32)
        mte = yr == TEST_YEAR
        if mte.any():
            te_parts.append(x[mte]); te_y_parts.append(lab[mte])
        mtr = keep[sl]
        if mtr.any():
            tr_parts.append(x[mtr]); tr_y_parts.append(lab[mtr])
        del x, yr, lab
    Xtr = np.vstack(tr_parts); ytr = np.concatenate(tr_y_parts)
    Xte = np.vstack(te_parts); yte = np.concatenate(te_y_parts)
    return Xtr, ytr, Xte, yte, names


def fit_eval(Xtr, ytr, Xte, yte, colmask: np.ndarray, tag: str) -> dict:
    Xtr_v, Xte_v = Xtr[:, colmask], Xte[:, colmask]
    t0 = time.time()
    m = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=42,
    ).fit(Xtr_v, ytr)
    proba = m.predict_proba(Xte_v)[:, 1]
    pred = (proba >= 0.5).astype(int)
    out = {
        "tag": tag,
        "n_feats": int(colmask.sum()),
        "roc_auc": round(float(roc_auc_score(yte, proba)), 4),
        "pr_auc": round(float(average_precision_score(yte, proba)), 4),
        "p05": round(float(precision_score(yte, pred, zero_division=0)), 4),
        "r05": round(float(recall_score(yte, pred, zero_division=0)), 4),
        "sec": round(time.time() - t0, 0),
    }
    del Xtr_v, Xte_v, proba
    return out


def main(cat: str) -> None:
    t0 = time.time()
    crit = set(VOCAB[cat]["critical"])
    # state index must match aggregate.STATES
    crit_idx = [i for i, s in enumerate(STATES) if s in crit]
    print(f"[{cat}] critical states: {[STATES[i] for i in crit_idx]}", flush=True)

    Xtr, ytr, Xte, yte, names = load_split(cat)
    print(f"[{cat}] train={len(ytr):,} (pos_rate={ytr.mean():.3f}) "
          f"test2026={len(yte):,} (pos_rate={yte.mean():.3f}) load={time.time()-t0:.0f}s", flush=True)

    n = len(names)
    idx = {nm_: i for i, nm_ in enumerate(names)}
    full = np.ones(n, dtype=bool)
    v1 = full.copy()
    if "since_act" in idx and "since_alar" in idx:
        v1[idx["since_act"]] = False
        v1[idx["since_alar"]] = False
    v2 = v1.copy()
    for nm_ in ("a7", "a30", "ar7", "ar30"):
        if nm_ in idx:
            v2[idx[nm_]] = False
    if "t7_" + STATES[0] in names:
        st7_base = names.index("t7_" + STATES[0])
        st30_base = names.index("t30_" + STATES[0])
        for i in crit_idx:
            v2[st7_base + i] = False
            v2[st30_base + i] = False

    results = [
        fit_eval(Xtr, ytr, Xte, yte, full, "V0 all"),
        fit_eval(Xtr, ytr, Xte, yte, v1, "V1 no since_*"),
        fit_eval(Xtr, ytr, Xte, yte, v2, "V2 history-only"),
    ]

    # zero-model diagnostics on 2026 (features are strictly pre-t, so valid)
    pos_mask = yte == 1
    print(f"\n[{cat}] SINGLE-FEATURE diagnostics on 2026:", flush=True)
    if "rep_gap" in idx:
        sl_rg = Xte[:, idx["rep_gap"]]
        print(f"  AUC(rep_gap) = {float(roc_auc_score(yte, sl_rg)):.4f}  "
              f"(==0: pos={float((sl_rg[pos_mask] == 0).mean()):.3f} neg={float((sl_rg[~pos_mask] == 0).mean()):.3f})")
    if "since_alar" in idx:
        sl_alar = Xte[:, idx["since_alar"]]
        print(f"  AUC(since_alar==0) = {float(roc_auc_score(yte, (sl_alar == 0).astype(int))):.4f}  "
              f"(==0: pos={float((sl_alar[pos_mask] == 0).mean()):.3f} neg={float((sl_alar[~pos_mask] == 0).mean()):.3f})")
    if "a7" in idx and "t7_" + STATES[0] in names:
        st7_base = names.index("t7_" + STATES[0])
        a7 = Xte[:, idx["a7"]]
        crit_t7 = np.stack([Xte[:, st7_base + i] for i in crit_idx], axis=1) if crit_idx else np.zeros((len(yte), 0))
        persist = (a7 > 0) | ((crit_t7 > 0).any(axis=1))
        print(f"[{cat}] ZERO-MODEL persistence rule (a7>0 or critical t7>0):", flush=True)
        print(f"  fires on {persist.mean():.3f} of rows | precision={float(precision_score(yte, persist.astype(int), zero_division=0)):.3f} recall={float(recall_score(yte, persist.astype(int), zero_division=0)):.3f}", flush=True)
    print(f"\n[{cat}] MODELS on 2026:", flush=True)
    for r in results:
        print(f"  {r['tag']:<16} feats={r['n_feats']:>3}  AUC={r['roc_auc']}  "
              f"PR-AUC={r['pr_auc']}  P@.5={r['p05']}  R@.5={r['r05']}  ({r['sec']:.0f}s)", flush=True)
    print(f"[{cat}] total {time.time()-t0:.0f}s\n", flush=True)


if __name__ == "__main__":
    import sys
    cats = sys.argv[1:] or ["sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"]
    for c in cats:
        main(c)
    print("AUDIT DONE", flush=True)
