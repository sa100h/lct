"""Smoke test: rebuild fire-risk 2019 into a temp FEAT dir, then verify the
new hour features (e7h_*/a7h_*/night_share7/peak_share7) against a direct
recomputation from agg-hour-2019.parquet, and check row/label counts match
the production features file for 2019."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "/home/junai/lct/ml-service")
import app.ingest.feature_engine as fe

TMP = Path("/tmp/hour_feat_smoke")
fe.FEAT = TMP  # redirect output
import shutil
if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)

BASE = Path("/home/junai/lct/ml-data")
sen = pd.read_csv(BASE / "справочник_каналов_датчиков.csv")
sen["cabinet"] = sen["тег_инженерной_системы"].astype(str).str.extract(r"^(\d+)-")[0]
import json
vocab = json.loads((BASE / "vocab.json").read_text(encoding="utf-8"))

fe.build_category("fire-risk", sen, years=[2019], crit_names=vocab["fire-risk"]["critical"])

out = TMP / "features-fire-risk.parquet"
new = pq.read_table(str(out)).to_pandas()
old = pq.read_table("/home/junai/lct/ml-data/features/features-fire-risk.parquet",
                    columns=["channel", "day", "year", "label"]).to_pandas()
old19 = old[old["year"] == 2019]
new19 = new[new["year"] == 2019].reset_index(drop=True)
old19 = old19.reset_index(drop=True)

print("cols:", len(new.columns), "feat cols:", len(new.columns) - 4)
print("rows new2019:", len(new19), "old2019:", len(old19))
same = (new19["channel"] == old19["channel"]).all() and (new19["day"] == old19["day"]).all() \
    and (new19["label"].astype(int) == old19["label"].astype(int)).all()
print("rows/labels aligned:", same)
assert same

# direct verification of hour features
h = pd.read_parquet("/home/junai/lct/ml-data/agg/agg-hour-2019.parquet",
                    columns=["channel", "day", "hour", "n_events", "n_alarm"])
h["day_ord"] = pd.to_datetime(h["day"]).astype("int64") // 10**9
h = h[h["channel"].isin(set(new19["channel"]))]

rng = np.random.default_rng(0)
idxs = rng.choice(len(new19), size=40, replace=False)
bad = 0
for i in idxs:
    r = new19.iloc[i]
    ch, day = r["channel"], r["day"].to_pydatetime().date()
    d_ord = (pd.Timestamp(day) - pd.Timestamp("1970-01-01")).days
    lo, hi = d_ord - 7, d_ord  # [t-7, t-1]
    sub = h[(h["channel"] == ch) & (h["day_ord"] >= lo) & (h["day_ord"] < hi)]
    # expected per-hour sums
    exp_ev = sub.groupby("hour")["n_events"].sum()
    exp_al = sub.groupby("hour")["n_alarm"].sum()
    for hr in range(24):
        got_e = float(r[f"e7h_{hr}"]); want_e = float(exp_ev.get(hr, 0))
        got_a = float(r[f"a7h_{hr}"]); want_a = float(exp_al.get(hr, 0))
        if abs(got_e - want_e) > 1e-3 or abs(got_a - want_a) > 1e-3:
            bad += 1
            print(f"  MISMATCH ch={ch} day={day} h={hr}: e {got_e} vs {want_e}, a {got_a} vs {want_a}")
    tot = float(sub["n_events"].sum())
    if tot > 0:
        want_n = sub[sub["hour"] < 6]["n_events"].sum() / tot
        want_p = sub[(sub["hour"] >= 8) & (sub["hour"] < 20)]["n_events"].sum() / tot
        if abs(float(r["night_share7"]) - want_n) > 1e-3 or abs(float(r["peak_share7"]) - want_p) > 1e-3:
            bad += 1
            print(f"  SHARE MISMATCH ch={ch} day={day}: night {r['night_share7']} vs {want_n:.4f}, peak {r['peak_share7']} vs {want_p:.4f}")
    else:
        if r["night_share7"] != 0 or r["peak_share7"] != 0:
            bad += 1
            print(f"  SHARE nonzero on zero-total ch={ch} day={day}")

# anti-leak: e7h must be zero for a day whose ONLY events in the window are
# on day t itself — check: for any emitted row, same-day hour counts must NOT
# appear. Spot check via first 7d of span: if channel's first report is the
# day itself, all e7h must be 0.
first_rows = []
for ch, grp in new19.groupby("channel"):
    if len(grp) >= 1:
        first = grp.iloc[0]
        if (first[[f"e7h_{x}" for x in range(24)]].sum() == 0 and
                first[[f"a7h_{x}" for x in range(24)]].sum() == 0):
            first_rows.append(1)
print("first-day rows with all-zero hour profile (expected: all):", len(first_rows), "/", new19["channel"].nunique())
print("MISMATCHES:", bad)
print("SMOKE", "FAIL" if bad else "PASS")
