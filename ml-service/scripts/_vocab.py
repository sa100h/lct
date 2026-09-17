"""Single pass over the full journal: per-category value vocabulary + critical counts.

Output: /home/junai/lct/ml-data/vocab.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EX = Path("/home/junai/lct/ml-data/extracted")
SEN = pd.read_csv("/home/junai/lct/ml-data/справочник_каналов_датчиков.csv")
COLS = ["ид_канала_данных", "тревожное", "значение_датчика"]

CATS = {
    "sensor-failure": None,
    "fire-risk": ["Пожарная охрана", "Температурная подсистема", "Газовая охрана"],
    "unauthorized-access": ["Охранная подсистема"],
    "infrastructure-wear": ["Диспетчерский контроль", "Диагностическая подсистема"],
}

CRITICAL = {
    "sensor-failure": ["Неисправен", "Обесточен", "Затоплен", "Не замкнут",
                       "Отключено устройство", "Много неисправных устройств",
                       "Питание от батарей"],
    "fire-risk": ["Обнаружен дым", "Внимание", "Опасность", "Обнаружен газ",
                  "Высокая температура", "Низкая температура", "Замыкание"],
    "unauthorized-access": ["Обнаружено движение", "Не замкнут", "Штаф",
                            "Обрыв", "Замыкание"],
    "infrastructure-wear": ["Неисправен", "Обесточен", "Отключено устройство",
                            "Много неисправных устройств", "Затоплен"],
}

TOP_K = 15


def main() -> None:
    sub_sets = {}
    for cat, subs in CATS.items():
        if subs is None:
            sub_sets[cat] = SEN[["ид_канала_данных"]].drop_duplicates()
        else:
            s = SEN[SEN["тип_инж_системы"].isin(subs)][["ид_канала_данных"]].drop_duplicates()
            sub_sets[cat] = s
            print(f"[{cat}] channels: {len(s)}")

    counts: dict[str, dict] = {c: {} for c in CATS}
    years = sorted(p.name for p in EX.iterdir() if p.is_dir())
    for year in years:
        f = EX / year / f"ext-journal-{year}.csv"
        if not f.exists():
            continue
        for cat in CATS:
            for chunk in pd.read_csv(f, usecols=COLS, dtype={"значение_датчика": "string"}, chunksize=4_000_000):
                chunk = chunk.dropna(subset=["ид_канала_данных"])
                chunk = chunk.merge(sub_sets[cat], on="ид_канала_данных", how="inner")
                vc = chunk["значение_датчика"].value_counts().to_dict()
                d = counts[cat]
                for k, v in vc.items():
                    d[k] = d.get(k, 0) + int(v)
        print(f"{year} done", flush=True)

    result = {}
    for cat, d in counts.items():
        top = [k for k, _ in sorted(d.items(), key=lambda kv: -kv[1])[:TOP_K]]
        vocab = list(dict.fromkeys(top + [c for c in CRITICAL[cat] if c in d]))
        print(f"[{cat}] n_unique={len(d)} vocab={len(vocab)}")
        for k in vocab:
            print(f"   {k!r}: {d.get(k, 0):,}")
        result[cat] = {
            "vocab": vocab,
            "critical": CRITICAL[cat],
            "counts": {k: d.get(k, 0) for k in vocab},
        }
    out = Path("/home/junai/lct/ml-data/vocab.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
