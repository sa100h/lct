# LCT — сервис прогнозной диагностики (Moskollektor)

Команда на хакатон **i.moscow** — сервис ML-прогноза аварий инженерных коллекторов по четырём направлениям: отказ датчика, пожарный риск, несанкционированный доступ, износ инфраструктуры.

## Архитектура

```
browser → api-proxy (YARP:80/443)
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

- API-шлюз: https://localhost (локальный самоподписанный сертификат)
- ML API через шлюз: https://localhost/api/ml/docs
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
cd web-frontend && pnpm install --frozen-lockfile && pnpm run dev
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

Локальный Compose по умолчанию оставляет только логи контейнеров Docker.
OpenTelemetry Collector, Tempo и Loki можно включить профилем `observability`;
Grafana и Prometheus пока закомментированы в `docker-compose.yml`.

<!-- NICEPLAN:BOARD -->

# 📋 NicePlan — LCT — прогнозная диагностика коллекторов (i.moscow)

> Git-native планирование в стиле [GitScrum](https://docs.gitscrum.com/en): задачи — markdown-файлы, статусы — в `tracker/tasks/`, этот раздел автогенерируется из них. Сменил задачу → `gen_dashboard.py` → коммит.

🗃️ **Backlog** 17 pts  📋 **To Do** 10 pts  🔨 **In Progress** 10 pts  🔎 **Review** 3 pts  ✅ **Done** 3 pts

| Backlog | To Do | In Progress | Review | Done |
|---|---|---|---|---|
| 🗃️ **`LCT-04`** Аналитика выгрузок организатора<br>_2 pt · Ildar · 2026-09-11_<br><br>🗃️ **`LCT-08`** Наблюдаемость: метрики + дашборд<br>_3 pt · artaktavi · 2026-09-12_<br><br>🗃️ **`LCT-09`** CI: тесты + сборка образов<br>_2 pt · Ildar · 2026-09-12_<br><br>🗃️ **`LCT-10`** Демо-данные и сценарий<br>_3 pt · Eduard · 2026-09-13_<br><br>🗃️ **`LCT-11`** Демо: стенд + репетиция<br>_3 pt · Ildar · 2026-09-14_<br><br>🗃️ **`LCT-12`** README/доска: синхронизация<br>_1 pt · artaktavi · 2026-09-08_<br><br>🗃️ **`LCT-13`** Презентация по проекту<br>_3 pt · sa100h · 2026-09-25_ | 📋 **`LCT-03`** Обучение и приёмка моделей<br>_5 pt · Eduard · 2026-09-10_<br><br>📋 **`LCT-07`** Фронтенд: дашборд + заявки<br>_5 pt · artaktavi · 2026-09-11_ | 🔨 **`LCT-02`** Ингест датчиков и признаки<br>_5 pt · Eduard · 2026-09-09_<br><br>🔨 **`LCT-06`** API: реестры, события, заявки<br>_5 pt · Ildar · 2026-09-10_ | 🔎 **`LCT-05`** Миграции доменной схемы БД<br>_3 pt · Ildar · 2026-09-09_ | ✅ **`LCT-01`** Контракт ML API согласован<br>_3 pt · Ildar · 2026-09-08_ |

## ⏳ Burndown

**Sprint 1 — протокол + ML core** — active

| День | Прошло дней | Осталось (факт) | Идеальный курс |
|---|---|---|---|
| | 7/7 | 40 pts ████████████████ | ░░░░░░░░░░░░░░░░ |

Готово: **3/43** pts из скоупа задач. Ёмкость спринта: 16 pts.

## 🏁 Хакатон: **i.moscow 2026**

Дедлайн: 2026-09-27 — осталось **11** дн. Продвижение отмечай в колонках и держи `LCT-12` живым.

<!-- NICEPLAN:/BOARD -->
