"""Smoke test: stream_split spatial join vs direct pandas merge (test split)."""
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.models.lgbm_model import stream_split

FD = "/home/junai/lct/ml-data/features/"
sp = pq.read_table(FD + "spatial.parquet").to_pandas()
sp_cols = [c for c in sp.columns if c not in ("channel", "day", "year")]
sp["k"] = sp["channel"] + "|" + sp["day"].dt.strftime("%Y-%m-%d")
sp = sp[["k"] + sp_cols].drop_duplicates("k").set_index("k")

res = stream_split(FD + "features-unauthorized-access.parquet",
                   train_max_year=2026, valid_year=2025, test_year=2026,
                   spatial_path=FD + "spatial.parquet")
names = res["names"]
print("spatial tail:", names[len(names) - len(sp_cols):])

fea = pq.read_table(FD + "features-unauthorized-access.parquet",
                    columns=["channel", "day", "year"]).to_pandas()
fea = fea[fea["year"] == 2026].reset_index(drop=True)
proba = res["Xte"]
k = fea["channel"] + "|" + fea["day"].dt.strftime("%Y-%m-%d")
merged = sp.reindex(k.to_numpy())

n = len(proba)
print("rows", n)
mism = 0
for j, c in enumerate(sp_cols):
    want = merged[c].to_numpy()
    got = proba[:, len(names) - len(sp_cols) + j]
    bad = ~np.isclose(got, want, equal_nan=True, atol=1e-6)
    if bad.any():
        mism += int(bad.sum())
        ii = np.flatnonzero(bad)[:3]
        print("MISMATCH", c, int(bad.sum()), [(k.iloc[i], got[i], want[i]) for i in ii])
print("total mismatches:", mism, "of", n * len(sp_cols))
nz = (proba[:, len(names) - len(sp_cols):] > 0)
print("nonzero-rate of spatial cols:", np.round(nz.mean(axis=0), 3))
