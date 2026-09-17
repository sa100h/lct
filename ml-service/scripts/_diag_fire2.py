"""Per-feature AUC scan on the 2026 fire-risk test set + date sanity."""
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.metrics import roc_auc_score

FEAT = "/home/junai/lct/ml-data/features/features-fire-risk.parquet"
pf = pq.ParquetFile(FEAT)
names = [c for c in pf.schema_arrow.names if c not in {"channel", "day", "year", "label"}]
print("day dtype:", pf.schema_arrow.field("day").type)

day_tab = pf.read(columns=["day"]).column(0)
d = pd.to_datetime(day_tab.to_pylist())
print("overall day range:", d.min(), "->", d.max())
for yy in range(2019, 2027):
    print(f"  {yy}: distinct calendar days with rows = {d[d.year == yy].nunique()}")

rows = []
for i in range(pf.metadata.num_row_groups):
    rg = pf.read_row_group(i, columns=["year", "label"] + names)
    yy = rg.column("year").to_numpy()
    mm = yy == 2026
    if not mm.any():
        continue
    rows.append({c: rg.column(c).to_numpy()[mm] for c in ["label"] + names})
y26 = np.concatenate([r["label"] for r in rows]).astype(int)
feats = {c: np.concatenate([r[c] for r in rows]).astype(np.float64) for c in names}

res = []
for c in names:
    x = feats[c]
    if np.unique(x).size < 2:
        continue
    a = roc_auc_score(y26, x)
    a = max(a, 1 - a)
    res.append((a, c))
res.sort(reverse=True)
print(f"\n2026 rows={len(y26):,} pos_rate={y26.mean():.4f}  per-feature AUC (top 25):")
for a, c in res[:25]:
    print(f"  {c:>10}  AUC={a:.4f}")
print("  ...")
for a, c in res[-5:]:
    print(f"  {c:>10}  AUC={a:.4f}")

top = [c for a, c in res[:5]]
for c in top:
    x = feats[c]
    print(f"\n{c}: pos median={np.median(x[y26 == 1]):.4f} neg median={np.median(x[y26 == 0]):.4f} "
          f"pos>0 rate={(x[y26 == 1] > 0).mean():.3f} neg>0 rate={(x[y26 == 0] > 0).mean():.3f}")
