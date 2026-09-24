"""One-shot validation of spatial features for 2025 (join + hand-check)."""
import sys

import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
import scripts.build_spatial_features as B

crit = B.critical_idx()
df = B.build_year(2025, crit)

f = pd.read_parquet(
    "/home/junai/lct/ml-data/features/features-fire-risk.parquet",
    columns=["channel", "day", "year"],
)
f25 = f[f.year == 2025][["channel", "day"]]
m = f25.merge(df, on=["channel", "day"], how="inner")
print("join: features25", len(f25), "matched", len(m))

crit_cols = [f"s_{k}" for k in crit]
a2 = pd.read_parquet(
    "/home/junai/lct/ml-data/agg/agg-2025.parquet",
    columns=["channel", "day", "n_alarm", "cabinet"] + crit_cols,
)
a2["day"] = pd.to_datetime(a2["day"])
a2["channel"] = a2["channel"].astype(str)
a2["d7"] = a2["day"] - pd.Timedelta(days=7)

checked = 0
mismatch = 0
for k in [0, 3, 5000, 10000, 25000]:
    row = m.iloc[k]
    ch = str(row["channel"])
    d0 = row["day"].normalize()
    d7 = d0 - pd.Timedelta(days=7)

    own = a2.query("channel == @ch and day == @d0", engine="python")
    if len(own) == 0:
        print("row", k, "ch", ch, "NOT FOUND")
        continue
    cab = own.iloc[0]["cabinet"]
    nbr = a2.query("cabinet == @cab and channel != @ch and day >= @d7 and day < @d0", engine="python")
    manual_alarm = float(nbr["n_alarm"].sum())
    manual_crit = float((nbr[crit_cols].sum(axis=1) > 0).sum())
    col_alarm = float(row["nbr_alarm7"])
    col_crit = float(row["nbr_crit7"])
    ok = abs(manual_alarm - col_alarm) < 1e-6 and abs(manual_crit - col_crit) < 1e-6
    if not ok:
        mismatch += 1
    checked += 1
    print(f"row {k} ch={ch} day={d0.date()} cab={cab} nbr_rows={len(nbr)}")
    print(f"   manual alarm={manual_alarm:.4f} crit={manual_crit:.4f}")
    print(f"   col    alarm={col_alarm:.4f} crit={col_crit:.4f}  ok={ok}")

print(f"\nchecked={checked} mismatch={mismatch}")
