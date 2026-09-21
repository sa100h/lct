"""Sanity-check hour-of-day aggregate vs day-granular (fixed merge)."""
import pandas as pd

AGG = "/home/junai/lct/ml-data/agg"
h = pd.read_parquet(f"{AGG}/agg-hour-2026.parquet")
d = pd.read_parquet(f"{AGG}/agg-2026.parquet")

hs = h.groupby(["channel", "day"], as_index=False)[["n_events", "n_alarm"]].sum()
dj = d[["channel", "day", "n_events", "n_alarm"]]
j = hs.merge(dj, on=["channel", "day"], suffixes=("_h", "_d"))
neq_e = int((j["n_events_h"] != j["n_events_d"]).sum())
neq_a = int((j["n_alarm_h"] != j["n_alarm_d"]).sum())
print(f"per (channel,day): hour-agg pairs={len(j)} day-agg pairs={len(d)} "
      f"n_events mismatches={neq_e} n_alarm mismatches={neq_a}")
print(f"hour-agg (channel,day,hour) rows={len(h)}  distinct hours/chanday min/median/max")
n_hours = h.groupby(["channel", "day"])["hour"].nunique()
print(f"  min={n_hours.min()} median={int(n_hours.median())} max={n_hours.max()} "
      f"(1 hour/day means reporting not spread across the day)")

# days covered: do hour-agg and day-agg cover identical day sets?
hd = set(h["day"].unique()); dd = set(d["day"].unique())
print(f"days: hour-agg={len(hd)} day-agg={len(dd)} only_in_hour={len(hd-dd)} only_in_day={len(dd-hd)}")

# events by hour across all data (unweighted activity profile)
prof = h.groupby("hour")["n_events"].sum().reindex(range(24)).fillna(0)
prof = prof / prof.sum()
print("\nactivity share by hour (0..23):")
for hh in range(24):
    bar = "#" * int(prof[hh] * 100)
    print(f"  {hh:02d}: {prof[hh]*100:5.2f}%  {bar}")
