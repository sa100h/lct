# ml-service (FastAPI)

ML-сервис прогнозной диагностики. Отдельный контейнер, которого не хватало в базовом шаблоне.

## Что внутри

| Путь | Назначение |
|------|-----------|
| `app/main.py` | FastAPI-приложение: `/predict`, `/retrain`, `/status`, `/healthz` |
| `app/schemas.py` | Pydantic-модели запросов/ответов |
| `app/models/features.py` | Схемы признаков по 4 категориям (6 признаков каждая) |
| `app/models/baseline.py` | Базовый тренер (HistGradientBoosting), синтетика или реальные данные |
| `app/models/registry.py` | Хранилище артефактов `models/<category>/` |
| `app/predict/engine.py` | Предсказание: risk score, label (порог 0.5), horizon |
| `app/ingest/loader.py` | Загрузка выгрузок организатора (`.xlsx`/`.csv`) |
| `app/ingest/feature_engine.py` | Сбор признаков по категориям (346 строк — ядро инжеста) |
| `app/ingest/aggregate.py` | Агрегация выгрузок в признаки (параметры cabinet/object) |
| `scripts/train.py` | CLI-обучение: `python -m scripts.train [--category fire-risk]` |
| `scripts/evaluate.py` | Precision/Recall по тестовой выборке (метрики приёмки) |
| `scripts/audit_leak.py` | Аудит утечки признаков (проверка rep_gap/side, label-дыры) |
| `tests/test_smoke.py` | Smoke-тесты (запускаются в CI) |

## Категории

| slug | направление |
|------|-------------|
| `sensor-failure` | отказ датчика |
| `fire-risk` | пожарный риск |
| `unauthorized-access` | несанкционированный доступ |
| `infrastructure-wear` | износ инфраструктуры |

## Данные

Кладите выгрузки организатора (xlsx-логи СМВУ, журналы ОДС, реестры) в
`ml-data/<category>/` — в Docker это монтируется как `/app/data:ro`.
После разбора признаков вызовите `POST /retrain`.

## Контейнер

| Параметр | Значение |
|----------|----------|
| Образ | `python:3.11-slim`, не-root `appuser` |
| Порт | `8000` (внутр. — наружу только через api-proxy) |
| Volumes | `ml_models:/app/models` (артефакты), `./ml-data:/app/data:ro` |
| Healthcheck | в compose не задан (только у postgres); `GET /status` — можно добавить |
| ENV | `ML_HORIZON_HOURS=24` |

`Dockerfile` — одноэтапный (pip install requirements → app + scripts).

## Локальный запуск

```bash
cd ml-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.train   # базовые модели
.venv/bin/uvicorn app.main:app --port 8000
# Swagger: http://localhost:8000/docs
```

## Тесты

```bash
.venv/bin/python -m pytest -q
```
