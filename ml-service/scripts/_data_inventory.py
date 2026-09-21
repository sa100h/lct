import json
import pyarrow.parquet as pq
import pyarrow.compute as pc

out = {}
for f, tag in [
    ("agg/agg-2019.parquet", "agg-day"),
    ("agg/agg-hour-2019.parquet", "agg-hour"),
]:
    pf = pq.ParquetFile(f"ml-data/{f}")
    out[tag] = {
        "rows": pf.metadata.num_rows,
        "cols": list(zip(pf.schema_arrow.names, [str(t) for t in pf.schema_arrow.types])),
    }

for name in ["agg", "agg-hour"]:
    yr = {}
    for y in range(2019, 2027):
        t = pq.read_table(f"ml-data/agg/{name}-{y}.parquet")
        yr[y] = {
            "rows": t.num_rows,
            "channels": pc.count_distinct(t.column("channel")).as_py(),
        }
    out[name + "_per_year"] = yr

for cat in ["sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"]:
    pf = pq.ParquetFile(f"ml-data/features/features-{cat}.parquet")
    t = pf.read(columns=["year", "label", "channel"])
    total = t.num_rows
    pos = pc.sum(t.column("label")).as_py()
    ch = pc.count_distinct(t.column("channel")).as_py()
    yrs = sorted(pc.unique(t.column("year")).to_pylist())
    out[f"feat-{cat}"] = {
        "rows": total,
        "pos": pos,
        "pos_rate": round(pos / total, 4),
        "channels": ch,
        "ncols": len(pf.schema_arrow.names),
        "years": yrs,
    }

print(json.dumps(out, ensure_ascii=False, indent=1))
