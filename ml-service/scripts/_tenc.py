"""Check тревожное raw encoding per year + fire/gas/access critical values in 2021-2022."""
from pathlib import Path

import pandas as pd

EX = Path("/home/junai/lct/ml-data/extracted")
COLS = ["ид_канала_данных", "тревожное", "значение_датчика"]
SEN = pd.read_csv("/home/junai/lct/ml-data/справочник_каналов_датчиков.csv")

for year in sorted(p.name for p in EX.iterdir() if p.is_dir()):
    f = EX / year / f"ext-journal-{year}.csv"
    if not f.exists():
        continue
    tvals = {}
    for chunk in pd.read_csv(f, usecols=["тревожное"], dtype={"тревожное": "string"}, chunksize=4_000_000):
        vc = chunk["тревожное"].value_counts(dropna=False).to_dict()
        for k, v in vc.items():
            tvals[str(k)] = tvals.get(str(k), 0) + int(v)
    print(year, tvals)
