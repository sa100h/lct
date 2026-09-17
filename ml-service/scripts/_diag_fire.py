import pyarrow.parquet as pq
import numpy as np

pf = pq.ParquetFile("/home/junai/lct/ml-data/features/features-fire-risk.parquet")
names = [c for c in pf.schema_arrow.names if c not in {"channel", "day", "year", "label"}]
print("n_feats:", len(names), "| has rep_gap:", "rep_gap" in names,
      "| idx:", names.index("rep_gap") if "rep_gap" in names else None)
cols = ["year", "label"] + names

parts_l, parts_a, parts_y = [], [], []
for i in range(pf.metadata.num_row_groups):
    rg = pf.read_row_group(i, columns=["year", "label", "a7"] + [f"t7_{j}" for j in range(26)])
    parts_y.append(rg.column("year").to_numpy())
    parts_l.append(rg.column("label").to_numpy().astype(np.int8))
    parts_a.append(rg.column("a7").to_numpy().astype(np.float64))
    if i == 0:
        parts_t7 = {j: [rg.column(f"t7_{j}").to_numpy().astype(np.float64)] for j in range(26)}
    else:
        for j in range(26):
            parts_t7[j].append(rg.column(f"t7_{j}").to_numpy().astype(np.float64))

y = np.concatenate(parts_y)
lab = np.concatenate(parts_l)
a7 = np.concatenate(parts_a)
t7 = {j: np.concatenate(v) for j, v in parts_t7.items()}

print("\npositive rate per year:")
for yy in range(2019, 2027):
    mm = y == yy
    print(f"  {yy}: rows={mm.sum():>8,} pos_rate={lab[mm].mean():.4f}")

m26 = y == 2026
lab26, a726 = lab[m26], a7[m26]
t726 = {j: v[m26] for j, v in t7.items()}
n = len(lab26)
print(f"\n2026: rows={n:,} pos={int(lab26.sum()):,} pos_rate={lab26.mean():.4f}")
print(f"a7>0 (alarm in prior 7d): overall={(a726 > 0).mean():.4f} | pos={(a726[lab26 == 1] > 0).mean():.4f} | neg={(a726[lab26 == 0] > 0).mean():.4f}")
print(f"pos rows with a7==0 (onset NOT preceded by alarm): {(a726[lab26 == 1] == 0).mean():.4f}")
cmax = np.stack([t726[j] for j in range(26)], axis=1)
cmax = cmax.max(axis=1)
print(f"crit state trail t7>0: pos={(cmax[lab26 == 1] > 0).mean():.4f} | neg={(cmax[lab26 == 0] > 0).mean():.4f}")
both = ((a726 > 0) | (cmax > 0))
print(f"rule (a7>0 | crit t7>0): fires on {both.mean():.4f} rows")
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score
print(f"  rule AUC={roc_auc_score(lab26, both.astype(int)):.4f} AP={average_precision_score(lab26, both.astype(int)):.4f}")
print(f"  rule P={precision_score(lab26, both.astype(int), zero_division=0):.4f} R={recall_score(lab26, both.astype(int), zero_division=0):.4f}")
