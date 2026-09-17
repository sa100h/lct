"""Confirm rep_gap==0  <=>  'channel reported on day t itself' (future leak)."""
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

FEAT = "/home/junai/lct/ml-data/features/features-fire-risk.parquet"
pf = pq.ParquetFile(FEAT)

ch_p, day_p, yr_p, lab_p, rep_p = [], [], [], [], []
for i in range(pf.metadata.num_row_groups):
    rg = pf.read_row_group(i, columns=["channel", "day", "year", "label", "rep_gap"])
    ch_p.append(rg.column("channel").to_numpy())
    day_p.append(np.asarray(rg.column("day").to_numpy(), dtype="datetime64[ms]").astype("int64"))
    yr_p.append(rg.column("year").to_numpy())
    lab_p.append(rg.column("label").to_numpy())
    rep_p.append(rg.column("rep_gap").to_numpy())

day = np.concatenate(day_p)  # ms since epoch
yr = np.concatenate(yr_p)
lab = np.concatenate(lab_p)
rep = np.concatenate(rep_p)

# independent check: reported-on-day-t means the same (channel, day) exists in the agg file
# here we only use the feature file: test the hypothesis via day-of-year patterns
m26 = yr == 2026
doy = pd.to_timedelta((day[m26] % 31536000000), unit="ms").days  # rough
print("rep_gap value counts (2026, top 10):")
print(pd.Series(rep[m26]).value_counts().sort_index().head(10))
print("rep_gap>0 share 2026:", round(float((rep[m26] > 0).mean()), 4))
print("\ncrosstab (rep_gap>0) x label, 2026:")
print(pd.crosstab(pd.Series((rep[m26] > 0).astype(int)), pd.Series(lab[m26])))
for v in (0, 1, 2, 5, 10):
    mm = (rep[m26] == v)
    if mm.any():
        print(f"rep_gap=={v}: n={mm.sum():,}  pos_rate={lab[m26][mm].mean():.3f}")
