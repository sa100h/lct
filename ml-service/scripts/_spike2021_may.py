"""2021 May: full bad-signal breakdown — daily, by cabinet/object/channel,
and the alarm-state mix that makes it 'bad'."""
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

AGG = "/home/junai/lct/ml-data/agg"
d = pd.read_parquet(f"{AGG}/agg-2021.parquet")
d["day"] = pd.to_datetime(d["day"]).dt.strftime("%Y-%m-%d")

may = d[(d["day"] >= "2021-05-01") & (d["day"] <= "2021-05-31")].copy()
may["bad"] = may[["s_3", "s_4"]].sum(axis=1)

# state mix for May: which s_i contributed to badness
st = [f"s_{i}" for i in range(30)]
st = [c for c in st if c in may.columns]
mm = may[st].sum().sort_values(ascending=False)
print("=== May 2021 state totals (non-zero) ===")
mm = mm[mm > 0]
for c in mm.index:
    i = int(c.split("_")[1])
    print(f"  {c}  {mm[c]:>10d}   {STATES[i]}")

# daily May with date labels
g = may.assign(day=may["day"]).groupby("day", as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"),
    s_brok=("s_3", "sum"), s_pow=("s_4", "sum"))
print("\n=== May 2021 daily (full month) ===")
print(g[["day", "n_events", "n_alarm", "s_brok", "s_pow"]].to_string(index=False))

print("\n=== May 2021: top cabinets by bad (Неисправен+Обесточен) ===")
cb = may.groupby("cabinet", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
cb["alarm_rate"] = (cb["n_alarm"] / cb["n_events"]).round(4)
print(cb.sort_values("bad", ascending=False).head(10).to_string(index=False))

print("\n=== May 2021: top objects by bad ===")
ob = may.groupby("ид_объект", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
print(ob.sort_values("bad", ascending=False).head(10).to_string(index=False))

print("\n=== May 2021: top channels by bad ===")
ch = may.groupby("channel", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
print(ch.sort_values("bad", ascending=False).head(15).to_string(index=False))

# Which channels are the broken cluster (95xxx) vs the 115xxx cluster?
print("\n=== May 2021: channel-family split (by 5-digit prefix) ===")
may["ch_prefix"] = may["channel"].astype(str).str[:2]
print(may.groupby("ch_prefix", dropna=False, as_index=False).agg(
    n_channels=("channel", "nunique"), n_events=("n_events", "sum"),
    bad=("bad", "sum")).sort_values("bad", ascending=False).to_string(index=False))
