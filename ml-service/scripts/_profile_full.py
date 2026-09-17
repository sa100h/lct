"""Profile the full journal (2019-2026): value vocabulary, date ranges, alarm rates."""
import pandas as pd
from pathlib import Path

EX = Path("/home/junai/lct/ml-data/extracted")
COLS = ["ид_события", "ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"]

for year in sorted(p.name for p in EX.iterdir() if p.is_dir()):
    f = EX / year / f"ext-journal-{year}.csv"
    if not f.exists():
        print(year, "MISSING", f)
        continue
    rows = 0
    alarms = 0
    alarm_rows = 0
    vals = {}
    dmin, dmax = None, None
    for chunk in pd.read_csv(f, usecols=COLS, chunksize=3_000_000):
        # files contain repeated header rows mid-file — drop them
        m = chunk["ид_события"].astype(str) != "ид_события"
        chunk = chunk[m]
        if chunk.empty:
            continue
        t = chunk["тревожное"].astype(str).str.lower()
        alarm_rows = int((t.isin(["true", "t", "1", "yes"])).sum())
        rows += len(chunk)
        vc = chunk["значение_датчика"].value_counts().to_dict()
        for k, v in vc.items():
            vals[k] = vals.get(k, 0) + int(v)
        dm = chunk["дата"].min()
        if dmin is None or dm < dmin:
            dmin = dm
        dm2 = chunk["дата"].max()
        if dmax is None or dm2 > dmax:
            dmax = dm2
    print(f"== {year}: rows={rows:,} alarm_rows={alarm_rows:,} date={dmin}..{dmax}")
    top = sorted(vals.items(), key=lambda kv: -kv[1])[:10]
    print("   top:", top)
    print("   n_unique_values:", len(vals))
    bad = [k for k in vals if isinstance(k, str) and k[:1].isdigit() is False and not k[0].isalpha()]
    print("   sample non-numeric non-alpha keys:", [k for k in list(vals)[:3]])
