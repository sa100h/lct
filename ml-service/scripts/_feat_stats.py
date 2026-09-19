"""Print row/col counts and per-year label stats for a features parquet."""
import sys
import pandas as pd
import pyarrow.parquet as pq

for path in sys.argv[1:]:
    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    nfeat = [c for c in names if c not in {"channel", "day", "year", "label"}]
    meta = {"year", "label"}
    tbl = pf.read(columns=sorted(meta))
    df = tbl.to_pandas()
    vc = df.groupby("year")["label"].agg(["count", "mean"]).round(4)
    print(f"== {path}")
    print(f"rows={pf.metadata.num_row_groups and df['label'].size:,} "
          f"ncols={len(names)} nfeat={len(nfeat)}")
    print(vc.to_string())
    print("last_feats:", nfeat[-6:])
