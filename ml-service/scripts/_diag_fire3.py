"""fire-risk label decomposition: how many 2026 positives are onset-only,
alarm-only, both, and how often onset days are preceded by a critical day."""
import json
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

AGG = "/home/junai/lct/ml-data/agg"
VOCAB = json.loads(open("/home/junai/lct/ml-data/vocab.json").read())
from importlib import import_module, sys
sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.aggregate import STATES

crit_names = set(VOCAB["fire-risk"]["critical"])
crit_idx = [i for i, s in enumerate(STATES) if s in crit_names]
print("critical states:", [STATES[i] for i in crit_idx])
s_cols = [f"s_{i}" for i in crit_idx]

for year in (2023, 2024, 2025, 2026):
    df = pq.read_table(AGG + f"/agg-{year}.parquet",
                       columns=["channel", "day", "n_alarm", *s_cols]).to_pandas()
    df = df.sort_values(["channel", "day"]).reset_index(drop=True)
    ch = df["channel"].to_numpy()
    days = pd.to_datetime(df["day"].to_numpy())
    al = df["n_alarm"].to_numpy().astype(bool)
    crit = (df[s_cols].to_numpy().astype(np.int8).sum(axis=1) > 0)
    prev_crit = np.zeros(len(df), bool)
    # previous row is the previous REPORT day; onset = critical & (new channel | previous report day not critical)
    ch_change = np.concatenate([[True], ch[1:] != ch[:-1]])
    onset = crit & (~np.concatenate([[False], crit[:-1]]) | ch_change)
    alarm_pos = al.sum()
    onset_only = (onset & ~al).sum()
    alarm_only = (al & ~onset).sum()
    both = (onset & al).sum()
    cont = (crit & ~onset).sum()  # critical-day that is a continuation
    lab = (al | onset).sum()
    print(f"\n{year}: channel-days={len(df):,}  critical_days={crit.sum():,} alarms={alarm_pos:,}")
    print(f"   label(alarm|onset)={lab:,}  alarm_only={alarm_only:,} onset_only={onset_only:,} both={both:,}")
    print(f"   critical continuation days (not label)={cont:,}  of critical days: {cont/max(crit.sum(),1):.1%}")
    print(f"   pos_rate among all rows={lab/len(df):.4f}")
