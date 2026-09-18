"""Verify the 2026-09-17 feature rebuild: schema + per-year row/label counts."""
from pathlib import Path

import pyarrow.parquet as pq

FEAT = Path("/home/junai/lct/ml-data/features")
NEW = ["month_sin", "month_cos", "dow", "cabinet", "object_code"]

for cat in ["sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"]:
    f = FEAT / f"features-{cat}.parquet"
    if not f.exists():
        print(f"[{cat}] MISSING {f}")
        continue
    t = pq.read_table(str(f))
    cols = t.column_names
    has_new = [c for c in NEW if c in cols]
    miss = [c for c in NEW if c not in cols]
    s = pq.read_table(str(f), columns=["year", "label"]).to_pandas()
    vc = s.groupby("year")["label"].agg(["count", "mean"])
    print(f"[{cat}] rows={len(s):,} cols={len(cols)} new_features={has_new} missing={miss}")
    print(vc.to_string())
    # sanity: cabinet/-1 spread on a sample
    cab = pq.read_table(str(f), columns=["cabinet", "object_code"]).to_pandas()
    print(f"  cabinet unique={cab['cabinet'].nunique()} (=-1:{(cab['cabinet'] == -1).mean():.3f}) "
          f"object_code unique={cab['object_code'].nunique()} (=-1:{(cab['object_code'] == -1).mean():.3f})")
    print()
