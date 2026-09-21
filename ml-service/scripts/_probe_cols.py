"""Check the FULL column set of the raw journal (aggregate.py reads only 4 cols).
Also inspect the sample journal CSV for a timestamp column.
"""
from pathlib import Path
import pandas as pd

EX = Path("/home/junai/lct/ml-data/extracted")

for y in [2019, 2025, 2026]:
    f = EX / str(y) / f"ext-journal-{y}.csv"
    # header only
    with open(f, encoding="utf-8", errors="replace") as fh:
        header = fh.readline().strip()
        line1 = fh.readline().strip()
    print(f"--- {y} ---")
    print("HEADER:", header)
    print("ROW1  :", line1[:400])

# sample journal CSV
p = Path("/home/junai/lct/ml-data/журнал_событий_пример.csv")
if p.exists():
    df = pd.read_csv(p, dtype=str, nrows=5)
    print("--- журнал_событий_пример.csv ---")
    print("COLUMNS:", list(df.columns))
    print(df.head(3).to_string(max_colwidth=40))
