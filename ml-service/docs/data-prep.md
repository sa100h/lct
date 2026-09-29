# Что нужно подготовить для запуска ml-service (данные и модели)

Контейнер `ml-service` данные **только читает**: `./ml-data` монтируется в
`/app/data` в режиме read-only. Внутри ничего не генерируется. Поэтому на
хосте должны лежать все артефакты — иначе сервис упадёт на старте (это
намеренно, см. «Если данных нет»).

| Путь на хосте | Внутри контейнера | Зачем |
|---|---|---|
| `ml-data/features/features-<кат>.parquet` | `/app/data/features/` | история каналов: 11 лагов + базовые фичи |
| `ml-data/features/features-<кат>-latest.parquet` | `/app/data/features/` | sidecar «последняя строка на канал» |
| `models/<кат>/model.lgb` + `meta.json` | `/app/models/` | сами модели |

`<кат>` — одна из `sensor-failure`, `fire-risk`, `unauthorized-access`,
`infrastructure-wear`. Полное описание самих файлов — `ml-data/DATA_CATALOG.md`
(§4 и §4.4). Поднять стек (обе части обязательны: без второй не публикуются
порты, без env podman-compose падает на `${AD_BIND_PASSWORD:?}`):

```bash
cd /home/junai/lct
set -a; . ./.env.e2e; set +a
podman-compose -f docker-compose.yml -f podman-compose.override.yml up -d --no-deps ml-service ml-broker
```

## Порядок сборки данных

```bash
cd /home/junai/lct/ml-service          # venv: ./.venv/bin/python

./.venv/bin/python -m app.ingest.aggregate  [годы...]  # → ../ml-data/agg/agg-<y>.parquet
./.venv/bin/python -m app.ingest.hour_agg   [годы...]  # → ../ml-data/agg/agg-hour-<y>.parquet
./.venv/bin/python -m app.ingest.feature_engine        # → ../ml-data/features/*.parquet
./.venv/bin/python -m scripts.build_latest_sidecars    # → ../ml-data/features/*-latest.parquet
./.venv/bin/python -m scripts.train --category <кат>   # → models/<кат>/   (LightGBM)
```

`build_latest_sidecars` **обязателен** после `feature_engine` — подробности
ниже. `--check` у него проверяет уже собранное, не пересобирая:

```bash
./.venv/bin/python -m scripts.build_latest_sidecars --check    # код 1, если что-то не так
```

## Три вещи, которые легко забыть

1. **Sidecar'ы обязаны существовать до старта.** Если
   `features-<кат>-latest.parquet` нет, `LagStore` попытается собрать его на
   месте — а запись в `/app/data` запрещена (read-only mount) → сервис
   падает на запросе. «Просто смонтировать папку с паркетами» недостаточно.

2. **Sidecar должен быть свежим.** Если он собран до последней пересборки
   фич, сервис молча кормит модель старым снимком — ничего не падает, но
   прогнозы неверны. Реальный случай (2026-09-29): два sidecar'а отставали
   на 3 дня и не содержали фич `f7`/`f30`, те подставлялись как `0.0`, хотя
   модель обучалась на реальных значениях. Поэтому — `--check` после каждой
   пересборки фич.

3. **Restart после пересборки.** Работающий контейнер держит sidecar'ы в
   памяти, новый файл сам он не увидит:

   ```bash
   podman restart lct_ml-service_1
   ```

## Модели: образ или volume

`/app/models` — это writable named volume (`ml_models`): в него пишет
`POST /retrain`, поэтому он не может быть частью read-only слоя образа.
Реальные артефакты при этом **запечены в образ** (`/app/models-baked`) и
копируются в volume на старте (`docker-entrypoint.sh`), если для категории
там ещё нет `meta.json`. Это даёт самодостаточное развёртывание: чистый хост
+ образ + смонтированные данные — и сервис поднимается с настоящими моделями,
без ручного `podman cp`.

## Если данных нет

`LCT_ALLOW_SYNTHETIC=false` выставлен в compose, поэтому сервис **не**
подменяет модель синтетической заглушкой — он падает с явной ошибкой:

```
RuntimeError: No feature file for '<кат>' at /app/data/features and
LCT_ALLOW_SYNTHETIC=false: ...
```

Это защита от того, что случилось 2026-09-28: из-за неверного пути к данным
`/retrain` не нашёл паркеты, обучил 6-фичевую синтетику и **затёр** ею
настоящие модели. Итог — одинаковый прогноз для всех датчиков.

Отдельно: если volume `ml_models` **пуст**, сервис на старте обучит модели
сам (`app/main.py`, `lifespan`), но движком `BaselineTrainer`
(HistGradientBoosting), а не продовым LightGBM — то есть получится модель
другого типа. На боксе с малым объёмом RAM это к тому же рискует упасть по
OOM. Поэтому модели привозят в образе или кладут в volume заранее.

## Проверка, что всё в порядке

```bash
curl -s http://127.0.0.1:18000/status | python3 -m json.tool
```

Ожидаемое: у всех 4 категорий `models.<кат>.engine` = `lightgbm-*`,
`lags.<кат>.status` = `ok` и `n_channels` = 11 482 / 6 830 / 2 209 / 2 443.
`lags.<кат>.status` = `empty` означает, что сервис не видит паркеты фич —
проблема с монтированием (`LCT_DATA_DIR`), а не с моделью.
