# LCT — сервис прогнозной диагностики (Moskollektor)

Команда на хакатон **i.moscow** — сервис ML-прогноза аварий инженерных коллекторов по четырём направлениям: отказ датчика, пожарный риск, несанкционированный доступ, износ инфраструктуры.

## Архитектура

```
browser → api-proxy (YARP:5000)
             ├── web-frontend   (Vue 3, :5173)
             ├── app-service    (ASP.NET Core, :8080) — БД, реестры, заявки
             └── ml-service     (FastAPI, :8000)   — ML-модели
   postgres (app_db: equipment, alarm_events, predictions, maintenance_requests)
```

## Быстрый старт

```bash
cp .env.example .env      # сменить пароли
docker compose up --build
```

- API-шлюз: http://localhost:5000
- ML-сервис напрямую: http://localhost:8000/docs
- Миграции применяются автоматически при старте app-service (набор `002_lct_domain.sql`)

### Локальная разработка без Docker

```bash
# ml-service
cd ml-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.train              # обучить базовые модели
.venv/bin/uvicorn app.main:app --port 8000

# app-service (MlService__BaseUrl=http://localhost:8000 по умолчанию)
dotnet run --project app-service

# web-frontend
cd web-frontend && npm ci && npm run dev
```

## ML-сервис

- **Эндпоинты**: `POST /predict`, `POST /retrain`, `GET /status`, `GET /healthz`
- **Модели**: по одной `HistGradientBoostingClassifier` на категорию,
  артефакты в `models/<category>/` (том `ml_models`)
- **Данные организатора**: выгрузки `.xlsx`/`.csv` — в `ml-data/`
  (монтируется как `/app/data:ro`), затем `POST /retrain`
- **Метрики приёмки**: Precision > 0.7, Recall > 0.5, горизонт ≥ 24 ч
  (`.venv/bin/python scripts/evaluate.py` печатает таблицу по тестовым выгрузкам)

См. [ml-service/README.md](ml-service/README.md).

## Наблюдательность

Grafana `http://localhost:3000` (admin / `GRAFANA_ADMIN_PASSWORD`),
Prometheus `:9090`, Tempo `:3200`, Loki `:3100`.
