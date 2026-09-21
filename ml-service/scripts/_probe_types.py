import pyarrow.parquet as pq
for f in ("agg-2022.parquet", "agg-hour-2022.parquet"):
    t = pq.read_table(f"/home/junai/lct/ml-data/agg/{f}")
    print(f, "->", {n: str(t.schema.field(n).type) for n in t.schema.names})
