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
там ещё нет `meta.json`. Те же четыре файла лежат и в git
(`ml-service/models/<кат>/{model.lgb,meta.json}`, ~2.6 МБ), поэтому клон
репозитория сразу даёт полный набор — без `podman cp` и без выгрузок.

Это даёт самодостаточное развёртывание: чистый хост
+ образ + смонтированные данные — и сервис поднимается с настоящими моделями,
без ручного `podman cp`.

## Переобучение по расписанию

`ml_schedule` **читает** `ml-broker`: воркер `SchedulerWorker`
(`ml-broker/app/scheduler_worker.py`) раз в 30 с забирает строки, у которых
`enabled` и `next_run_at <= now()`, и для `kind='retrain'` вызывает
`POST /retrain`, записывая прогон в `ml_retrain_runs` (подробности —
`ml-broker/README.md`). Сеяное `daily-retrain` (`30 4 * * *`, UTC) активно,
то есть переобучение запускается само; `hourly-predict` отключена миграцией
`039_disable_predict_all_schedule.sql` — вид `predict-all` не реализован.

**Важно про движок.** `POST /retrain` обучает **HistGradientBoosting**
(`app/models/baseline.py` → артефакт `model.joblib`), а не продовый LightGBM:
продовые `model.lgb` получены ручным запуском `scripts/train.py` (по умолчанию
`--engine lgbm`). Значит, прогон по расписанию заменит артефакт категории на
`model.joblib` и удалит `model.lgb` из volume.

Данные при переобучении не создаются: и `/retrain`, и `scripts/train.py` читают
одни и те же `features-<кат>.parquet`, поэтому пересборка данных — всегда
отдельный ручной шаг (см. «Порядок сборки данных»). Паркеты статичны, а сплит
детерминирован (train — `year < 2026`, test — `2026`, seed 42), поэтому ночной
прогон на неизменных данных даёт тот же результат, меняя только версию.

## Что будет при старте, если чего-то нет

Поведение зависит от двух независимых вещей: есть ли модели в `/app/models`
(их привозит образ) и видны ли паркеты в `/app/data/features`. Проверено
запуском самого `lifespan` и контейнера:

| Модели | Данные | Что происходит при старте |
|---|---|---|
| есть (из образа) | есть | Норма. `lags.<кат>.status = ok` |
| есть (из образа) | нет | Сервис **поднимается** и работает, но ошибки не падает: `LagStore` пишет warning на каждую категорию, `lags.<кат>.status = empty`, и **все** прогнозы — `applicable=false, prediction=null`. Видно в `/status`; выдуманных чисел нет |
| нет (артефакты удалены) | есть | Сервис обучает 4 категории **на старте** (`app/main.py`, `lifespan` → `BaselineTrainer`), но движком HistGradientBoosting (`model.joblib`) — это **не** продовый LightGBM. Долго, на малой RAM риск OOM |
| нет (артефакты удалены) | нет | `RuntimeError: No feature file for '<кат>' ... LCT_ALLOW_SYNTHETIC=false` → контейнер **не стартует** |

Артефакты моделей теперь и в git (`ml-service/models/<кат>/{model.lgb,meta.json}`),
и в образе, поэтому две нижние строки — это следствие ручного удаления, а не
нормальный сценарий. Раньше «нет моделей» было штатным для чистой копии
репозитория; теперь нет.

Последний случай — это защита от инцидента 2026-09-28: тогда из-за неверного
пути к данным `/retrain` не нашёл паркеты, обучил 6-фичевую синтетику и
**затёр** ею настоящие модели. Итог — одинаковый прогноз для всех датчиков.
`LCT_ALLOW_SYNTHETIC=false` (в compose) запрещает эту подмену: и на старте, и
в `/retrain` отсутствие данных приводит к явной ошибке.

Практический вывод: **данные — единственное, что обязательно готовить руками.**
Модели приезжают в образе, а третий сценарий (самообучение на HGB) — это
аварийный путь, а не штатный.

## Проверка, что всё в порядке

```bash
curl -s http://127.0.0.1:18000/status | python3 -m json.tool
```

Ожидаемое: у всех 4 категорий `models.<кат>.engine` = `lightgbm-*`,
`lags.<кат>.status` = `ok` и `n_channels` = 11 482 / 6 830 / 2 209 / 2 443.
`lags.<кат>.status` = `empty` означает, что сервис не видит паркеты фич —
проблема с монтированием (`LCT_DATA_DIR`), а не с моделью.
