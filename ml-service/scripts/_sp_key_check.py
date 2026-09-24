"""Verify spatial.parquet join-key uniqueness + day alignment with feature files."""
import pyarrow.parquet as pq

sp = pq.ParquetFile("/home/junai/lct/ml-data/features/spatial.parquet")
print("spatial cols:", [x.name for x in sp.schema_arrow],
      "day type:", sp.schema_arrow.field("day").type,
      "ch type:", sp.schema_arrow.field("channel").type)

ch = sp.read_row_group(0, columns=["channel"]).column("channel").to_pylist()[:5]
dy = sp.read_row_group(0, columns=["day"]).column("day").to_pylist()[:5]
print("sample ch:", ch)
print("sample day:", dy)

# full key uniqueness
tch = sp.read(columns=["channel"]).column("channel").to_pylist()
tdy = sp.read(columns=["day"]).column("day").to_pylist()
n = len(tch)
keys = set(zip(tch, tdy))
print("rows", n, "unique keys", len(keys), "dup" if n != len(keys) else "OK unique")
# midnight check
from datetime import time
nonmid = sum(1 for d in tdy if d.time() != time(0, 0))
print("non-midnight days:", nonmid)
del tch, tdy, keys

# feature file day alignment
fp = pq.ParquetFile("/home/junai/lct/ml-data/features/features-sensor-failure.parquet")
fdy = fp.read_row_group(0, columns=["day"]).column("day").to_pylist()[:5]
fch = fp.read_row_group(0, columns=["channel"]).column("channel").to_pylist()[:5]
print("feat sample ch:", fch)
print("feat sample day:", fdy)
nonmid_f = sum(1 for d in fdy if d.time() != time(0, 0))
print("feat non-midnight:", nonmid_f)
