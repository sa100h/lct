# Как посмотреть результаты агрегирования (pandas)

Артефакты лежат в `/home/junai/lct/ml-data/agg/` (подробности схем — `ml-data/DATA_CATALOG.md` §2–3):

- `agg/agg-<год>.parquet` — дневное зерно: 1 строка = (канал, день). Колонки: `channel`, `day`, `cabinet`, `ид_объект`, счётчики событий/тревог (`n_events`, `n_alarm`), состояния `s_0…s_N`, числовые статистики `num_sum/sq/min/max`, `n_num`.
- `agg/agg-hour-<год>.parquet` — часовое зерно: те же колонки + `hour` (0–23; `-1` — строки без `время` в журнале). Строки только там, где события были (без нулевой развёртки на 24 часа).

Запуск через venv ml-service (pandas + pyarrow уже там):

```bash
cd /home/junai/lct/ml-service && .venv/bin/python
```

## Быстрый старт

```python
import pandas as pd
pd.set_option("display.max_columns", 50)
pd.set_option("display.width", 200)

AGG = "/home/junai/lct/ml-data/agg"
d = pd.read_parquet(f"{AGG}/agg-2026.parquet")        # дневной (325k строк в 2026)
h = pd.read_parquet(f"{AGG}/agg-hour-2026.parquet")   # часовой

d.info()          # типы и null'и
d.head()          # первые строки
```

Читайте только нужные колонки, чтобы не тащить весь файл в память:
`pd.read_parquet(f"{AGG}/agg-2026.parquet", columns=["channel","day","n_events","n_alarm"])`.

## По каналу (история конкретного датчика)

`subject_id` / канал = строка, например `"103904"`:

```python
d[d.channel == "103904"]                       # дневная история канала (52 дня в 2026)
h[h.channel == "103904"].groupby("hour")[["n_events","n_alarm"]].sum()  # часовой профиль
```

## Сверки и профили

```python
# Часовой профиль на всю пачку: какие часы самые «тревожные»
h.groupby("hour")[["n_events","n_alarm"]].sum()

# Конвенция hour=-1 (строки без времени в журнале)
h[h.hour == -1].shape   # ожидается 0 null в hour, строки с -1 = «время отсутствовало»

# Top-каналы по тревогам за год
d.nlargest(10, "n_alarm")[["channel","cabinet","ид_объект","n_events","n_alarm"]]

# Сколько уникальных каналов/объектов
d.channel.nunique(), d.ид_объект.nunique()   # в 2026: ~11 487 каналов, 95 объектов

# Резервное сравнение: суммарные события по годам (быстрые контрольные суммы)
for y in range(2019, 2027):
    t = pd.read_parquet(f"{AGG}/agg-{y}.parquet", columns=["n_events","n_alarm"])
    print(y, t.n_events.sum(), t.n_alarm.sum())
```

## Сверка hour ↔ daily (качество агрегата)

Полный автоматический рекап — скрипт `scripts/_reconcile_hour.py` (сверка сворачивания по (channel, day) с daily-файлами, 0 расхождений по 8 годам):

```bash
cd /home/junai/lct/ml-service && .venv/bin/python scripts/_reconcile_hour.py
```

Ручной вариант по подмножеству:

```python
agg_hour = h.groupby(["channel","day"], as_index=False)[["n_events","n_alarm"]].sum()
merged = agg_hour.merge(d[["channel","day","n_events","n_alarm"]], on=["channel","day"], suffixes=("_h","_d"))
(merged.n_events_h == merged.n_events_d).all(), (merged.n_alarm_h == merged.n_alarm_d).all()
```

## Осторожно

- Годы 2019–2025 по `agg-hour-*` ~16–20 MB каждый — по одному в памяти, не concat'ить все 8 лет в один DataFrame без нужды (3.8 GB box).
- Состояния: индексы `s_<i>` — по `STATES` из `app/ingest/aggregate.py` (`s_0` = «Норма», `s_1` = «Неопределен», …).
- Колонки `cabinet`/`ид_объект` — categorical, значения из справочника каналов; NaN = канал вне справочника.
- Ссылки на расчёт фич из этих агрегатов: `app/ingest/feature_engine.py` (в т.ч. 50 hour-фич из `agg-hour-*`).
