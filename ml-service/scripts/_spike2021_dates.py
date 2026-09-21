"""2021 spike: exact dates + intra-day hour profile of the worst periods."""
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

AGG = "/home/junai/lct/ml-data/agg"
d = pd.read_parquet(f"{AGG}/agg-2021.parquet")
d["day"] = pd.to_datetime(d["day"])
print("day dtype:", d["day"].dtype)

# daily totals with real dates, Apr-Jul
d["mday"] = d["day"].dt.strftime("%Y-%m-%d")
g = (d.assign(mday=d["day"].dt.strftime("%Y-%m-%d"))
     .groupby("mday", as_index=False)
     .agg(n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"),
          s_brok=("s_3", "sum"), s_pow=("s_4", "sum")))
w = g[(g["mday"] >= "2021-04-25") & (g["mday"] <= "2021-07-10")].copy()
w = w[(w["s_brok"] > 300) | (w["s_pow"] > 1000) | (w["n_alarm"] > 1500)]
print("\n=== 2021: anomaly days (Apr25-Jul10) ===")
print(w[["mday", "n_events", "n_alarm", "s_brok", "s_pow"]].to_string(index=False))

# hour profile for the May 11-19 window (the big 'Неисправен' plateau)
try:
    h = pd.read_parquet(f"{AGG}/agg-hour-2021.parquet")
    h["day"] = pd.to_datetime(h["day"])
    win = h[(h["day"] >= "2021-05-11") & (h["day"] <= "2021-05-19")]
    hh = win.groupby("hour", as_index=False).agg(
        n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"),
        s_brok=("s_3", "sum"), s_pow=("s_4", "sum"))
    print("\n=== May 11-19 2021 by hour (the 'Неисправен' plateau) ===")
    print(hh.to_string(index=False))
except FileNotFoundError:
    print("\n(hour-agg 2021 not ready yet)")

# Also check the June 'Обесточен' spike dates: find which days had s_pow > 1000
print("\n=== 2021 Jun: days with s_pow (Обесточен) > 1000 ===")
june = g[(g["mday"] >= "2021-06-01") & (g["mday"] <= "2021-06-30")].copy()
print(june[june["s_pow"] > 1000][["mday", "n_events", "n_alarm", "s_brok", "s_pow"]].to_string(index=False))

# Which channel family drives the June Obestochon spike?
june_d = d[(d["day"] >= "2021-06-01") & (d["day"] <= "2021-06-30")].copy()
ch = june_d.groupby("channel", as_index=False).agg(
    n_events=("n_events", "sum"), s_pow=("s_4", "sum"), s_brok=("s_3", "sum"))
print("\n=== 2021 June: top channels by Обесточен ===")
print(ch.sort_values("s_pow", ascending=False).head(12).to_string(index=False))

# Time-of-day on the top June anomaly days
top_days = june.sort_values("s_pow", ascending=False).head(3)["mday"].tolist()
top_set = set(top_days)
try:
    h2 = pd.read_parquet(f"{AGG}/agg-hour-2021.parquet")
    h2["day"] = pd.to_datetime(h2["day"]).dt.strftime("%Y-%m-%d")
    h3 = h2[h2["day"].isin(top_set)]
    print(f"\n=== hour profile on top-3 June anomaly days {top_days} ===")
    print(h3.groupby("hour", as_index=False).agg(
        n_events=("n_events", "sum"), s_pow=("s_4", "sum"), s_brok=("s_3", "sum")).to_string(index=False))
except FileNotFoundError:
    print("\n(hour-agg 2021 not ready yet for hour profile)")
