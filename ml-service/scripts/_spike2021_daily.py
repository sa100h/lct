"""2021 May-June spike: daily trend Apr-Jul + localization by cabinet/object/channel."""
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

AGG = "/home/junai/lct/ml-data/agg"
d = pd.read_parquet(f"{AGG}/agg-2021.parquet")
d["day"] = pd.to_datetime(d["day"])

# daily totals
g = d.groupby("day", as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"),
    s_brok=("s_3", "sum"),   # Неисправен
    s_pow=("s_4", "sum"),    # Обесточен
    s_flood=("s_5", "sum"),  # Затоплен
    s_batt=("s_8", "sum"),   # Питание от батарей
    s_numprev=("s_1", "sum"),  # Неопределен
)
w = g[(g["day"] >= "2021-04-01") & (g["day"] <= "2021-07-31")].copy()
for c in ["n_events", "n_alarm", "s_brok", "s_pow"]:
    w[c] = w[c].astype(int)
pd.set_option("display.width", 200)
print("=== daily Apr-Jul 2021: events, alarms, Неисправен, Обесточен ===")
print(w[["n_events", "n_alarm", "s_brok", "s_pow"]].to_string())

# 3-day rolling to smooth
r = w["s_brok"].rolling(3).mean().round(0)
print("\nНеисправен 3d-rolling mean:")
print(r.to_string())

# Which cabinets/objects drive May-June bad states?
def window(a, b):
    m = d[(d["day"] >= a) & (d["day"] <= b)]
    base = m[["channel", "cabinet", "ид_объект", "n_events", "n_alarm", "s_3", "s_4"]].groupby(
        ["cabinet", "ид_объект"], dropna=False).sum(numeric_only=True)
    base = base[base["n_events"] > 0]
    base["alarm_rate"] = (base["n_alarm"] / base["n_events"]).round(4)
    return base.sort_values("s_3 + s_4", ascending=False) if hasattr(base, "add") else None

mayjune = d[(d["day"] >= "2021-05-01") & (d["day"] <= "2021-06-30")].copy()
mayjune["bad"] = mayjune[["s_3", "s_4"]].sum(axis=1)
print("\n=== May-June 2021: top cabinets by (Неисправен+Обесточен) ===")
cb = mayjune.groupby("cabinet", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
cb["alarm_rate"] = (cb["n_alarm"] / cb["n_events"]).round(4)
print(cb.sort_values("bad", ascending=False).head(12).to_string())

print("\n=== May-June 2021: top objects by bad states ===")
ob = mayjune.groupby("ид_объект", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
ob["alarm_rate"] = (ob["n_alarm"] / ob["n_events"]).round(4)
print(ob.sort_values("bad", ascending=False).head(12).to_string())

print("\n=== May-June 2021: top channels by bad states (device level) ===")
ch = mayjune.groupby("channel", dropna=False, as_index=False).agg(
    n_events=("n_events", "sum"), n_alarm=("n_alarm", "sum"), bad=("bad", "sum"))
print(ch.sort_values("bad", ascending=False).head(15).to_string())
