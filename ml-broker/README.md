# ml-broker

Брокер между БД и ml-service: следит за очередью новых признаков, батчит
субъектов, вызывает `POST /predict_all_batch` на ml-service и пишет прогнозы
в `predictions`. Один asyncio-процесс: пул БД + потребитель очереди с
retry/backoff и восстановлением разорванных батчей + пробуждение по каналу
`LISTEN` + HTTP-сервер `/healthz` (порт 8080).

Пути в этом README — относительно корня репозитория. Образ собирается
**всегда из всего репозитория** (`docker build .` — из корня): внутри
`Dockerfile` пути `ml-broker/…` указаны относительно корня сборки.

## Как работает

1. Новые признаки появляются в `sensor_features`; триггер
   `trg_enqueue_features` фанат их в `ml_predict_queue` (по одному ряду
   на категорию) и стучит по каналу `ml_predict`.
2. Потребитель опрашивает очередь (интервал `POLL_SECONDS`) и собирает батч
   до `FORECAST_BATCH_CHUNK` субъектов.
3. Один `POST /predict_all_batch` на ml-service; ответы батча кладутся в
   `predictions` (idempotent upsert, дедуп по `uq_queue_dedup`).
4. Если батч превысил `PREDICT_TIMEOUT_SECONDS` — батч режется пополам
   (минимальный кусок — 25 субъектов), неудачные куски пробуются снова.
5. Неудача — повторы с backoff `RETRY_BACKOFF_SECONDS`, максимум
   `MAX_ATTEMPTS`. Разорванные «в полёте» батчи (orphan-running)
   восстанавливаются автоматически.
6. `NotifierWorker` слушает канал `lct_ml_forecast` — внешние события (например
   из app-service) пробуждают потребителя, а polling остаётся страховкой.

## Требования

- postgres со схемой `app_db` (миграции в `postgres-db/migrations/app_db/`;
  в стеке применяются автоматически при старте app-service, в том числе таблицы
  `ml_predict_queue`, `predictions`);
- ml-service в той же docker-сети (в стеке поднимается сам compose-сервис
  `ml-service`, по умолчанию `http://ml-service:8000`).

## Развёртывание

### Полный стек (рекомендуется)

```bash
git clone https://github.com/sa100h/lct.git
cd lct
cp .env.example .env      # задать APP_DB_PASSWORD (и POSTGRES_PASSWORD)
docker compose up --build
```

ml-broker стартует после готовности postgres и ml-service; ключевые параметры
берутся из compose (в `.env` — `APP_DB_PASSWORD`, `FORECAST_BATCH_CHUNK`,
`PREDICT_TIMEOUT_SECONDS`).

### Один контейнер

```bash
docker build -t lct/ml-broker .          # из корня репозитория
docker run --rm \
  -e DB_DSN='postgresql://app_service:***@postgres:5432/app_db' \
  -e ML_BASE_URL='http://ml-service:8000' \
  -e FORECAST_BATCH_CHUNK=300 \
  -e PREDICT_TIMEOUT_SECONDS=600 \
  lct/ml-broker
```

Если postgres и ml-service подняты **на этом же хосте**, достаточно:

```bash
docker run --rm --network host -e LOG_LEVEL=DEBUG lct/ml-broker
```

(defaults в DSN: `host=127.0.0.1 port=5432 db=app_db user=app_service`)

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DB_DSN` | `postgresql://app_service:***@127.0.0.1:5432/app_db` | postgres: URI или key=value (asyncpg-style) |
| `ML_BASE_URL` | `http://127.0.0.1:8000` | base URL ml-service |
| `FORECAST_BATCH_CHUNK` | `300` | субъектов в одном `predict_all_batch` |
| `PREDICT_TIMEOUT_SECONDS` | `600` | бюджет одного батч-вызова, с |
| `POLL_SECONDS` | `5` | опрос очереди, с |
| `MAX_ATTEMPTS` | `3` | повторы батча |
| `RETRY_BACKOFF_SECONDS` | `10` | backoff между повторами, с |
| `HEALTH_PORT` | `8080` | `/healthz` |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING` |
| `APP_SERVICE_CALLBACK_URL` / `APP_SERVICE_LOGIN` / `APP_SERVICE_PASSWORD` | `http://app-service:8081/api/v1/forecasts/notify` / `lct` / пусто | callback в app-service (опционально) |

## Проверка

```bash
# из стека:
docker compose exec ml-broker curl -fs localhost:8080/healthz
curl -fs http://<хост>/api/ml/predict          # smoke через шлюз (опционально)
docker compose exec postgres psql -U app_service -d app_db \
  -c 'SELECT category, COUNT(*) FROM predictions GROUP BY category ORDER BY category;'
```

В логах: `ml-broker starting` … `predict_all_batch ok` — признак живого цикла.

## Тесты

```bash
cd ml-broker
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```
