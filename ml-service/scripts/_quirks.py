"""Check data quirks: тревожное encoding, inline headers, 2026 file, category channel counts."""
import pandas as pd
from pathlib import Path

EX = Path("/home/junai/lct/ml-data/extracted")

# 1) тревожное distinct values in 2019 + 2026
for year in ["2019", "2026"]:
    f = EX / year / f"ext-journal-{year}.csv"
    if not f.exists():
        print(year, "missing")
        continue
    print(f"\n== {year} file: {f} exists={f.exists()} size={f.stat().st_size/1e6:.1f}MB")
    n_rows = 0
    tvals = {}
    hdr_rows = 0
    for chunk in pd.read_csv(f, chunksize=2_000_000, names=None, dtype=str):
        # detect inline header rows
        if "ид_события" in chunk.columns:
            hdr_rows += int((chunk["ид_события"].astype(str).str.strip() == "ид_события").sum())
        tc = chunk["тревожное"].astype(str).str.strip().str.lower()
        vc = tc.value_counts().to_dict()
        for k, v in vc.items():
            tvals[k] = tvals.get(k, 0) + int(v)
        n_rows += len(chunk)
    print("   rows:", f"{n_rows:,}", " inline-header rows:", hdr_rows)
    print("   тревожное value counts:", tvals)

# 2) sample file (2026-08-01) тревожное encoding
s = pd.read_csv("/home/junai/lct/ml-data/журнал_событий_пример.csv", dtype=str)
print("\nsample file тревожное:", s["тревожное"].astype(str).str.strip().str.lower().value_counts().to_dict())

# 3) category channel counts from sensor directory
sd = pd.read_csv("/home/junai/lct/ml-data/справочник_каналов_датчиков.csv")
print("\nsensor directory total channels:", len(sd))
print("system counts:")
print(sd["тип_инж_системы"].value_counts().to_string())
# category -> sensor type filter
cat_map = {
    "sensor-failure": None,  # all (device-fault states)
    "fire-risk": {"Пожарная охрана", "Температурная подсистема", "Газовая охрана"},
    "unauthorized-access": {"Охранная подсистема"},
    "infrastructure-wear": {"Диспетчерский контроль", "Диагностическая подсистема"},
}
for cat, sysset in cat_map.items():
    if sysset is None:
        n = len(sd)
    else:
        n = sd["тип_инж_системы"].isin(sysset).sum()
    print(f"   {cat}: {n} channels")
