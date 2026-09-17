"""Cross-check: does rep_gap==0 exactly equal 'channel reported on day t' (future info)?"""
import pyarrow.parquet as pq

fea = pq.read_table(
    "/home/junai/lct/ml-data/features/features-fire-risk.parquet",
    columns=["channel", "day", "year", "label", "rep_gap"],
).to_pandas()
fea = fea[fea.year == 2026]
agg = pq.read_table(
    "/home/junai/lct/ml-data/agg/agg-2026.parquet", columns=["channel", "day"]
).to_pandas()
rep_days = set(zip(agg.channel, agg.day.astype(str)))
fea["day_s"] = fea.day.astype(str)
fea["reported_today"] = [c in rep_days for c in zip(fea.channel, fea.day_s)]
n = len(fea)
a = fea.rep_gap.eq(0).astype(bool)
b = fea.reported_today.astype(bool)
print(f"rows 2026: {n:,}")
print(f"(rep_gap==0) == reported_today: {(a == b).mean():.5f}")
print(f"rep_gap==0 but NOT reported today: {(a & ~b).sum():,}")
print(f"reported today but rep_gap>0: {(b & ~a).sum():,}")
print(f"label==1 all have rep_gap==0? {bool(fea[fea.label==1].rep_gap.eq(0)).__bool__() if len(fea[fea.label==1]) else None}")
