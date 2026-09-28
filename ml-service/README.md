# ml-service (FastAPI)

ML-сервис прогнозной диагностики четырёх категорий: `sensor-failure`,
`fire-risk`, `unauthorized-access`, `infrastructure-wear`. Отдельный
контейнер; в полном стеке порт 8000 доступен только внутри compose-сети —
снаружи ML-API ходит через api-proxy по префиксу `/api/ml`.

Все пути в этом README — относительно корня репозитория (каталог, где лежит
`docker-compose.yml`). Образ собирается **всегда из всего репозитория**
(`docker build .` — из корня): внутри `Dockerfile` пути `ml-service/…`
указаны относительно корня сборки.

## Эндпоинты

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/healthz` | GET | liveness-проверка (не зависит от моделей) |
| `/status` | GET | readiness: состояние моделей и данных |
| `/predict` | POST | прогноз одной категории: `subject_id` + признаки |
| `/predict_all` | POST | все 4 категории за одного субъекта |
| `/predict_all_batch` | POST | батч-прогноз: список субъектов × 4 категории за один вызов |
| `/retrain` | POST | переобучение моделей по выгрузкам организатора |

Swagger: `/docs`.

## Развёртывание

### Полный стек (рекомендуется)

```bash
git clone https://github.com/sa100h/lct.git
cd lct
cp .env.example .env      # задать POSTGRES_PASSWORD и APP_DB_PASSWORD
docker compose up --build
```

ml-service стартует после готовности postgres. Из браузера:
`https://<хост>/api/ml/docs` (локальный самоподписанный сертификат).

### Один контейнер

```bash
docker build -t lct/ml-service .
docker run --rm -p 8000:8000 lct/ml-service
```

Без моделей и данных сервис поднялся и отвечает на `/healthz`; прогнозы
придут после `POST /retrain` (или загрузки артефактов во volume).

## Что монтируется и какие переменные

| Параметр | Значение |
|----------|----------|
| образ | `python:3.11-slim`, не-root `appuser` |
| порт | `8000` |
| volume `/app/models` | артефакты моделей — в стеке named volume `ml_models`, переживает перезапуски |
| volume `/app/data:ro` | выгрузки организатора (`.xlsx`/`.csv`) — опционально, можно любой каталог с файлами (в compose это `ml-data/`) |
| env | `ML_HORIZON_HOURS=24` — горизонт прогноза в часах; других обязательных переменных нет |

## Данные и переобучение

1. Выгрузки (.xlsx/.csv) кладутся в каталог, смонтированный в `/app/data`
   — в стеке это `ml-data/` в корне репозитория (путь можно заменить любым в
   compose: `<any-dir>:/app/data:ro`).
2. `POST /retrain` (из стека: `https://<хост>/api/ml/retrain`).
3. `GET /status` — модели пересобраны, видна версия данных.

## Проверка

```bash
curl -fs https://<хост>/api/ml/healthz      # 200
curl -fs https://<хост>/api/ml/status       # состояние моделей
```

Внутри сети: `docker compose exec ml-service curl -fs localhost:8000/status`.

## Локальный запуск без Docker (по желанию)

```bash
cd ml-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.train             # базовые модели
.venv/bin/uvicorn app.main:app --port 8000    # Swagger: http://localhost:8000/docs
```

## Тесты

```bash
.venv/bin/python -m pytest -q
```