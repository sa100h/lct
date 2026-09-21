"""Probe the raw journal's `дата` column: does it carry hour-of-day, and for which years?"""
from pathlib import Path
import pandas as pd

EX = Path("/home/junai/lct/ml-data/extracted")
COLS = ["ид_канала_данных", "дата", "тревожное", "значение_датчика"]

for y in range(2019, 2027):
    f = EX / str(y) / f"ext-journal-{y}.csv"
    if not f.exists():
        print(f"{y}: MISSING {f}")
        continue
    chunk = pd.read_csv(f, usecols=COLS, dtype=str, chunksize=200_000, low_memory=False).__next__()
    d = chunk["дата"].dropna().astype(str)
    n = len(d)
    # distribution of string lengths -> reveals date vs datetime format
    lens = d.str.len().value_counts().to_dict()
    samples = d.unique()[:8].tolist()
    dt = pd.to_datetime(d, errors="coerce")
    hours = dt.dt.hour
    h_dist = hours.value_counts(normalize=True).sort_index().to_dict()
    n_times = int(dt.notna().sum())
    print(f"{y}: n={n} len_dist={lens} times={n_times}/{n} "
          f"samples={samples}")
    if n_times:
        print(f"   hour_dist(first200k)={ {int(k): round(v,3) for k,v in h_dist.items()} }")
