"""NicePlan: создаёт tracker/tasks/*.md (seed). Повторный запуск переписывает seed-задачи."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tracker" / "tasks"
TASKS.mkdir(parents=True, exist_ok=True)

T = """---
id: {id}; title: {title}; column: {column}; points: {points}; assignee: {assignee}; due: {due}; tags: {tags}
---
# {id} — {title}

{body}

## Чек-лист
{checks}
"""

seed = [
("LCT-01","Контракт ML API согласован","Done",3,"Ildar","2026-09-08","ml;backend",
 "FastAPI ml-service отвечает контракту: `POST /predict` (категория, признакный вектор → вероятность, интерпретация), `GET /status` (модели, метрики), `GET /healthz`. Схемы зафиксированы в `ml-service/app/schemas.py` и `app-service/Contracts/PredictionContracts.cs`, синхронизированы по обе стороны.\n\nРешения: горизонт прогноза 24 ч; по одной модели на категорию; контракты — source of truth для фронтенда.",
 ["- [x] Описать Pydantic-схемы запроса/ответа","- [x] Отразить в C#-контрактах app-service","- [x] Понятить smoke-тест под контракт"]),
("LCT-02","Ингест датчиков и признаки","In Progress",5,"Eduard","2026-09-09","ml;data",
 "Пайплайн: выгрузки организатора (`.xlsx`/`.csv` в `ml-data/`) → нормализация (время UTC, ID оборудования) → признаки для всех четырёх категорий: отказ датчика, пожарный риск, несанкционированный доступ, износ. Код в `ml-service/app/ingest/loader.py` и `app/models/features.py`.",
 ["- [x] Парсинг образцовых выгрузок","- [ ] Нормализация времени/ID по всем выгрузкам","- [ ] Признаки для категории «износ»","- [ ] Юнит-тесты loader"]),
("LCT-03","Обучение и приёмка моделей","To Do",5,"Eduard","2026-09-10","ml",
 "Базовые `HistGradientBoostingClassifier` на категорию, артефакты в `models/<category>/` (том `ml_models`). Принять по метрикам организатора: Precision > 0.7, Recall > 0.5, горизонт ≥ 24 ч. Таблицу метрик печатает `scripts/evaluate.py`.",
 ["- [x] Пайплайн train.py + реестр моделей","- [ ] Прогон на всех выгрузках","- [ ] Таблица метрик → в demo","- [ ] Достичь порога Precision/Recall"]),
("LCT-04","Аналитика выгрузок организатора","Backlog",2,"Ildar","2026-09-11","data;ml",
 "Разведка: распределения, Missing, дрейфы между выгрузками; что реально обучается, где шов. Итог — заметка `tracker/notes/data-recon.md`, решения по признакам — в LCT-02.",
 ["- [ ] Статистика по каждой выгрузке","- [ ] Отчёт о качествах данных","- [ ] Рекомендации по признакам"]),
("LCT-05","Миграции доменной схемы БД","Review",3,"Ildar","2026-09-09","backend;db",
 "Набор `002_lct_domain.sql` в `postgres-db/migrations/app_db/`: equipment, alarm_events, predictions, maintenance_requests + индексы по времени/оборудованию. Через `shared/DatabaseMigration/PostgresMigrator.cs` (idempotent) применяется автоматически при старте app-service. Чекать идемпотентность на пустой БД и на уже заполненной.",
 ["- [x] Миграции написаны","- [x] Idempotency на чистой и заполненной БД","- [x] Индексы под запросы дашборда"]),
("LCT-06","API: реестры, события, заявки","In Progress",5,"Ildar","2026-09-10","backend",
 "ASP.NET Core app-service: CRUD по реестру оборудования; загрузка alarm_events; список прогнозов (по оборудованию и горизонтам); создание и ведение maintenance_requests; клиент ml-service (`Ml/MlServiceClient.cs`).",
 ["- [x] Реестр equipment","- [x] Запись alarm_events","- [ ] Отчёт прогнозов с фильтром","- [ ] Жизненный цикл заявок"]),
("LCT-07","Фронтенд: дашборд + заявки","To Do",5,"artaktavi","2026-09-11","frontend",
 "Vue 3 + Naive UI: вид «Сводка» (карта/список оборудования, badges прогнозов), вид «Заявки» (создание, статусы), фильтр по горизонтам и категориям. API-клиент — `src/api/app.ts`. Демо-сценарий: «увидеть прогноз → создать заявку → закрыть».",
 ["- [x] Каркас: App/Router/theme","- [ ] Вид Сводка","- [ ] Вид Заявки","- [ ] Фильтры и состояния","- [ ] Тёмная/светлая тема"]),
("LCT-08","Наблюдаемость: метрики + дашборд","Backlog",3,"artaktavi","2026-09-12","ops",
 "Prometheus `:9090`, Grafana `:3000`, Tempo `:3200`, Loki `:3100` уже в compose. Сделать: дашборд «Хакатон LCT» (QPS, латентность предиктов, свежие прогнозы, статусы моделей). Конфиги: `observability/`.",
 ["- [ ] Дашборд Grafana (JSON)","- [ ] Метрики ml-service (predict time, fallback)","- [ ] Трассировка браузер → api → ml"]),
("LCT-09","CI: тесты + сборка образов","Backlog",2,"Ildar","2026-09-12","ci",
 "`.github/workflows/ci.yml`: тесты (app-service.Tests, ml-service/tests, oxlint+eslint для фронта), сборка Docker-образов для публичной проверки. Не убить quick demo: таймауты и кэши.",
 ["- [ ] Тесты проходят в CI","- [ ] Docker-сборка всех сервисов","- [ ] Кэши npm/pip/dotnet"]),
("LCT-10","Демо-данные и сценарий","Backlog",3,"Eduard","2026-09-13","data;demo",
 "Скрипт генерации правдоподобного demo-набора (оборудование, события, прогнозы, заявки) — чтобы на демо система жила. Сценарий на 5 минут: 3 экрана, 1 live-предикт, 1 закрытая заявка. Файл: `scripts/demo_seed.py` + заметка `tracker/notes/demo-script.md`.",
 ["- [ ] Генератор демо-данных","- [ ] Сценарий с репликами","- [ ] Дроп-кейс: план Б (без интернета)"]),
("LCT-11","Демо: стенд + репетиция","Backlog",3,"Ildar","2026-09-14","demo;ops",
 "Финальная сборка: deploy.yml в GHCR (`sha-<commit>`), запуск compose на демо-машине, TLS через proxy. Репетиция x2, чек-лист запуска/остановки, роли у жюри. Привязка к D-1.",
 ["- [ ] Deploy в демо-окружение","- [ ] Репетиция 1 (внутренняя)","- [ ] Репетиция 2 (под демо)","- [ ] Runbook: падение/восстановление"]),
("LCT-12","README/доска: синхронизация","Backlog",1,"artaktavi","2026-09-08","docs",
 "README репозитория держит канбан-сводку и burndown (автогенерация из `tracker/`). Правило: сменил статус задачи → `gen_dashboard.py` → коммит. Workflow `dashboard.yml` делает это автоматически на main.",
 ["- [x] генератор написан","- [x] workflow настроен","- [ ] Проверяем автообновление на PR"]),
]

for (id_, title, col, pts, who, due, tags, body, checks) in seed:
    checks_md = "\n".join(checks)
    p = TASKS / f"{id_}.md"
    p.write_text(T.format(id=id_, title=title, column=col, points=pts,
                          assignee=who, due=due, tags=tags, body=body,
                          checks=checks_md), encoding="utf-8")
    print("wrote", p.name)
