"""2021 May-June bad-signal spike: monthly + state mix."""
import json
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

AGG = "/home/junai/lct/ml-data/agg"
BASE = "/home/junai/lct/ml-data"

d = pd.read_parquet(f"{AGG}/agg-2021.parquet")
d["day"] = pd.to_datetime(d["day"])
d["month"] = d["day"].dt.month

vocab = json.loads(open(f"{BASE}/vocab.json", encoding="utf-8").read())
print("=== vocab categories & critical states ===")
for cat, v in vocab.items():
    print(f"  {cat}: {v['critical']}")

print("\n=== STATES (s_0..s_25) ===")
for i, s in enumerate(STATES):
    print(f"  s_{i}: {s}")

g = d.groupby("month").agg(n_days=("day", "nunique"), n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"))
g["alarm_rate"] = (g["n_alarm"] / g["n_events"]).round(4)
print("\n=== 2021 by month ===")
print(g.to_string())

st = [f"s_{i}" for i in range(len(STATES))]
sm = d.groupby("month")[st].sum().T
sm = sm.set_axis([STATES[i] for i in range(len(STATES))], axis=0)
sm = sm[sm.sum(axis=1) > 0]
print("\n=== state counts by month (only non-zero states) ===")
print(sm.to_string())
