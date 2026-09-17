"""Per-feature AUC on the FIXED fire-risk 2026 test set (leak-free file)."""
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.metrics import roc_auc_score

FEAT = "/home/junai/lct/ml-data/features/features-fire-risk.parquet"
pf = pq.ParquetFile(FEAT)
names = [c for c in pf.schema_arrow.names if c not in {"channel", "day", "year", "label"}]

rows = []
X26, y26, Xpre, ypre = [], [], [], []
for i in range(pf.metadata.num_row_groups):
    rg = pf.read_row_group(i, columns=["year", "label"] + names)
    yy = rg.column("year").to_numpy()
    mm = yy == 2026
    lab = rg.column("label").to_numpy()
    X = np.column_stack([rg.column(c).to_numpy() for c in names]).astype(np.float64)
    if mm.any():
        X26.append(X[mm]); y26.append(lab[mm])
    if (~mm).any():
        Xpre.append(X[~mm]); ypre.append(lab[~mm])
X26 = np.vstack(X26); y26 = np.concatenate(y26)

print(f"2026 rows={len(y26):,} pos_rate={y26.mean():.3f} | train rows={sum(len(x) for x in Xpre):,}")
out = []
for j, c in enumerate(names):
    x = X26[:, j]
    if x.std() == 0:
        continue
    try:
        a = roc_auc_score(y26, x)
    except Exception:
        continue
    out.append((c, a))
out.sort(key=lambda t: -abs(t[1] - 0.5))
print("\ntop |AUC-0.5| features on 2026 (fixed file):")
for c, a in out[:20]:
    print(f"  {c:<14} AUC={a:.4f}")
print("\nbottom (worst):")
for c, a in out[-5:]:
    print(f"  {c:<14} AUC={a:.4f}")
