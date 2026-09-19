"""Reconcile agg-hour-<y> rolled to (channel, day) vs agg-<y> — all years.

Both stages share the same raw filters (TRUE|FALSE тревожное), the same
invalid-reading mask and the same EXCLUDE_SPANS, so the hour aggregate
collapsed to (channel, day) must be cell-identical to the day aggregate.
Checks: key-set equality, n_events / n_alarm / s_* sums, max abs diff.
"""
import sys
import pandas as pd

sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import N_STATES

AGG = "/home/junai/lct/ml-data/agg"
YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
S_COLS = [f"s_{i}" for i in range(N_STATES)]
E_COLS = ["n_events", "n_alarm"] + S_COLS

print(f"{'year':<7}{'day_rows':>10}{'hour_rows':>10}{'pairs':>9}{'only_day':>9}{'only_hour':>10}{'mismatch':>9}{'max_diff':>9}")
all_ok = True
for y in YEARS:
    d = pd.read_parquet(f"{AGG}/agg-{y}.parquet")
    h = pd.read_parquet(f"{AGG}/agg-hour-{y}.parquet")
    hr = h.groupby(["channel", "day"], as_index=False)[E_COLS].sum()

    m = d.merge(hr, on=["channel", "day"], how="outer", indicator=True)
    only_day = int((m["_merge"] == "left_only").sum())
    only_hour = int((m["_merge"] == "right_only").sum())
    both = m[m["_merge"] == "both"]

    n_mis = 0
    max_diff = 0.0
    for c in E_COLS:
        a = both[f"{c}_x"].to_numpy()
        b = both[f"{c}_y"].to_numpy()
        n_mis += int((a != b).sum())
        max_diff = max(max_diff, float(abs(a - b).max())) if len(a) else 0.0

    ok = only_day == 0 and only_hour == 0 and n_mis == 0
    all_ok = all_ok and ok
    print(f"{y:<7}{len(d):>10,}{len(h):>10,}{len(both):>9,}{only_day:>9,}{only_hour:>10,}{n_mis:>9,}{max_diff:>9.1f}  {'OK' if ok else 'MISMATCH'}")

print("\nRECONCILE ALL:", "PASS" if all_ok else "FAIL")
