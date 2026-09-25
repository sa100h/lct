import sys
import pandas as pd
sys.path.insert(0, "/home/junai/lct/ml-service")
import scripts.build_spatial_features as B

crit = B.critical_idx()
print("builder crit idx:", crit)
print("builder crit cols:", [f"s_{k}" for k in crit])
a2 = pd.read_parquet(
    "/home/junai/lct/ml-data/agg/agg-2025.parquet",
    columns=["channel", "day", "cabinet"] + [f"s_{k}" for k in crit],
)
a2["day"] = pd.to_datetime(a2["day"])
ch = "104026"
d0 = pd.Timestamp("2025-07-23")
d7 = d0 - pd.Timedelta(days=7)
win = a2.query(
    "cabinet == 360 and channel != @ch and day >= @d7 and day < @d0",
    engine="python",
)
print("nbr rows", len(win), "crit", int((win[[f"s_{k}" for k in crit]].sum(axis=1) > 0).sum()),
      "alarm", float(win.n_alarm.sum()))
