"""2021 full-year monthly alarm + bad-state table, and the alarm driver in late April."""
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

AGG = "/home/junai/lct/ml-data/agg"
d = pd.read_parquet(f"{AGG}/agg-2021.parquet")
d["day"] = pd.to_datetime(d["day"])
d["month"] = d["day"].dt.month

g = d.groupby("month", as_index=False).agg(
    n_days=("day", "nunique"), n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"),
    s_brok=("s_3", "sum"), s_pow=("s_4", "sum"), s_doblet=("s_24", "sum"), s_batt=("s_8", "sum"))
g["alarm_rate"] = (g["n_alarm"] / g["n_events"]).round(4)
print("=== 2021 full year by month ===")
print(g.to_string(index=False))

# late-April plateau: by cabinet + alarm state mix
ap = d[(d["day"] >= "2021-04-25") & (d["day"] <= "2021-04-30")].copy()
ap["bad"] = ap[["s_3", "s_4"]].sum(axis=1)
print("\n=== Apr 25-30 2021: state mix ===")
st = [c for c in [f"s_{i}" for i in range(30)] if c in ap.columns]
mx = ap[st].sum().sort_values(ascending=False)
for c in mx.index:
    if mx[c] > 100:
        i = int(c.split("_")[1])
        print(f"  {c}  {mx[c]:>10d}   {STATES[i]}")

print("\n=== Apr 25-30 2021: top cabinets by bad ===")
cb = ap.groupby("cabinet", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
cb["alarm_rate"] = (cb["n_alarm"] / cb["n_events"]).round(4)
print(cb.sort_values("bad", ascending=False).head(12).to_string(index=False))

print("\n=== Apr 25-30 2021: top channels by bad (with s_3 breakdown) ===")
ch = ap.groupby("channel", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"), s_3=("s_3", "sum"))
print(ch.sort_values("bad", ascending=False).head(15).to_string(index=False))

# channel family
ap["ch_prefix"] = ap["channel"].astype(str).str[:2]
print("\n=== Apr 25-30 2021: channel-family split ===")
print(ap.groupby("ch_prefix", dropna=False, as_index=False).agg(
    n_channels=("channel", "nunique"), n_events=("n_events", "sum"),
    bad=("bad", "sum")).sort_values("bad", ascending=False).head(10).to_string(index=False))
