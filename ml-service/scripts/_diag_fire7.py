import numpy as np
import pyarrow.parquet as pq

pf = pq.ParquetFile("/home/junai/lct/ml-data/features/features-fire-risk.parquet")
print("num_row_groups:", pf.metadata.num_row_groups)
yr = pf.read(columns=["year"]).column(0).to_numpy()
print("total rows:", len(yr))
print("year counts:", {int(k): int(v) for k, v in zip(*np.unique(yr, return_counts=True))})
