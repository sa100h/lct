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
| `scripts/train.py` | CLI-обучение: `python -m scripts.train [--category fire-risk]` |
| `scripts/evaluate.py` | Precision/Recall по тестовой выборке (метрики приёмки) |
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
