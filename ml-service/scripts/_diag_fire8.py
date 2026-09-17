"""2026 fire-risk label composition: alarm vs state-onset; onset-after-gap share.

With intermittent reporting, a persistent critical state re-appearing after a
reporting gap reads as a 'new onset' (t-1 calendar day is zero). Measure how
much of the 2026 positive label is that artifact, per year.
"""
import numpy as np
import sys

sys.path.insert(0, "/home/junai/lct/ml-service")
import pyarrow.parquet as pq

AGG = "/home/junai/lct/ml-data/agg"
FEAT = "/home/junai/lct/ml-data/features/features-fire-risk.parquet"

# critical states for fire-risk from vocab.json (mirror of feature_engine logic)
import json
VOCAB = json.loads(open("/home/junai/lct/ml-data/vocab.json", encoding="utf-8").read())
CRIT = set(VOCAB["fire-risk"]["critical"])
from app.ingest.aggregate import STATES
N = len(STATES)
crit_idx = [i for i, s in enumerate(STATES) if s in CRIT]

# which channels belong to fire-risk? reuse feature_engine mapping
import pandas as pd, sys
sys.path.insert(0, "/home/junai/lct/ml-service")
from app.ingest.feature_engine import cat_channels
sen = pd.read_csv("/home/junai/lct/ml-data/справочник_каналов_датчиков.csv")
chset = cat_channels(["Пожарная охрана", "Температурная подсистема", "Газовая охрана"], sen)

for year in (2024, 2025, 2026):
    df = pd.read_parquet(f"{AGG}/agg-{year}.parquet",
                         columns=["channel", "day"] + [f"s_{i}" for i in range(N)] + ["n_alarm"])
    df = df[df["channel"].isin(chset)].sort_values(["channel", "day"])
    crit = (df[[f"s_{i}" for i in crit_idx]] > 0).any(axis=1).astype(int)
    # onset = critical today & not critical yesterday (per calendar day within segment)
    al = df["n_alarm"].fillna(0).to_numpy()
    crit_n = crit.to_numpy()
    onset = np.zeros(len(df), bool)
    onset[0] = crit_n[0]
    onset[1:] = (crit_n[1:] > 0) & (crit_n[:-1] == 0)
    # alarm-only vs state-onset vs both
    both = (al > 0) & onset
    alarm_only = (al > 0) & ~onset
    onset_only = onset & (al <= 0)
    pos = (al > 0) | onset
    print(f"\n{year}: channel-days={len(df):,}  positives={pos.sum():,} ({pos.mean():.3f})")
    print(f"  alarm rows: {(al>0).sum():,} ({(al>0).mean():.3f}) | state-onset rows: {onset.sum():,} ({onset.mean():.4f}) | both: {both.sum():,}")
    # onset-after-gap: previous CALENDAR day (not row) missing
    days = pd.to_datetime(df["day"].to_numpy()).to_numpy()
    dord = (days.astype("int64") // 86_400_000_000_000).astype(np.int64)
    same_ch = (df["channel"].to_numpy()[1:] != df["channel"].to_numpy()[:-1])
    prev_gap = np.zeros(len(df), bool)
    prev_gap[1:] = (dord[1:] - dord[:-1] > 1) | same_ch
    onset_g = onset & prev_gap
    onset_c = onset & ~prev_gap
    print(f"  onsets after a GAP day: {onset_g.sum():,} ({onset_g.mean():.4f}) | after consecutive day: {onset_c.sum():,} ({onset_c.mean():.4f})")
    # of the 'new onset' positives, what fraction is gap artifact?
    onset_pos = onset  # onset is part of the label
    print(f"  gap-onsets as share of onset-positives: {onset_g.sum() / max(onset.sum(),1):.2f}")
