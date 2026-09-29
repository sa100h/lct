# Отчёт: проект LCT (Москоллكتور)
**Дата:** 2026-09-29 · **Репозиторий:** `sa100h/lct` · **Система:** ML-прогноз аварий инженерных коллекторов

---

## 1. Что это
Сервис ML-прогнозной диагностики по 4 направлениям:
- **Об отказе датчика** (sensor-failure)
- **По пожарной опасности** (fire-risk)
- **По несанкционированному доступу** (unauthorized-access)
- **По износу инфраструктуры** (infrastructure-wear)

---

## 2. Составные части проекта

| # | Компонент | Стек | Роль |
|---|-----------|------|------|
| 1 | **web-frontend** | React 19 + Vite 8, antd 6, echarts 6, Redux Toolkit, react-router 7, i18next | SPA: дашборд, карта коллекторов, прогнозы, заявки, история, настройки |
| 2 | **api-proxy** | .NET 10 + YARP 2.3 | API-шлюз: `/api/app` → app-service, `/api/ml` → ml-service; статика фронтенда; TLS 80/443 |
| 3 | **app-service** | ASP.NET Core 10, Npgsql, Novell.LDAP, QuestPDF | Бизнес-ядро: реестры объектов/каналов/состояний, события, заявки, PDF-отчёты, JWT auth |
| 4 | **ml-service** | Python 3.11, FastAPI, Uvicorn, Pydantic, **LightGBM 4.7**, pandas, PyArrow, scikit-learn | Ядро ML: `/predict`, `/predict_all`, `/predict_all_batch`, `/retrain`, `/status`; 4 модели |
| 5 | **ml-broker** | Python 3.11, asyncio, asyncpg, httpx, structlog | Оркестратор между app и ML: очередь `ml_predict_queue`, retry (3×), scheduler (retrain по крену), маппинг каналов |
| 6 | **ml-data-prep** | Python 3.11 (pandas/numpy/PyArrow, asyncpg; без LightGBM) | Ночной refresh: `events_log` → Parquet-фичи + sidecars + trigger retrain |
| 7 | **test-event-feeder** | FastAPI + uvicorn, p7zip | FastAPI-эмулятор внешнего журнала событий (E2E) |
| 8 | **ad** | Samba AD DC (`nowsci/samba-domain`) | LDAP/LDAPS-аутентификация, домен `lct.ru` |
| 9 | **shared** | C# (PostgresMigrator, JWT, OTel-билдер) | Общие библиотеки: миграции, auth, телеметрия |
| 10 | **observability** | OTel Collector, Tempo, Loki, Promtail, Prometheus, Grafana, node-exporter | Трассировка, логи, метрики, дашборды |
| 11 | **postgres-db** | PostgreSQL + SQL-мigrations (001–040) | БД `app_db` + init-скрипты |
| 12 | **ml-data** | Parquet + CSV/7z | Данные: события 2019–2026, агрегаты (`agg/`), фичи (`features/`), модели, погода |
| 13 | **tracker** | Git-native NicePlan | Канбан-доска |

---

## 3. Функциональные контейнеры

| Контейнер | База | Порт | Задача |
|-----------|------|------|--------|
| **postgres** | postgres:18 (dev) / 15 (deploy) | 5432 | БД `app_db` |
| **api-proxy** | .NET 10 + node-build | 80 / 443 | Reverse proxy + TLS + статика |
| **app-service** | .NET 10 ASP.NET Core | 8080 | Бизнес-логика, auth, реестры |
| **ml-service** | python:3.11-slim (uvicorn) | 8000 | ML-модели, predict/retrain |
| **ml-data-prep** | python:3.11-slim | — | Nightly refresh данных |
| **ml-broker** | python:3.11-slim (asyncpg) | 8080 | Очередь, scheduler, retrain |
| **test-event-feeder** | python:3.11-slim (p7zip) | 8000 | Эмуляция внешнего журнала |
| **ad** | nowsci/samba-domain | — | LDAP/LDAPS |
| **loki / tempo / otel-collector / prometheus / grafana / promtail / node-exporter** | Grafana stack | — | Observability (только deploy) |

**Volumes:** `postgres_data`, `ml_models` (модели), `ad_data`/`ad_config`/`ad_public_certs` (AD certs), `event_feed_cache`.

**Безопасность:** 3 сервиса (`ml-service`, `ml-broker`, `api-proxy`) работают с `read_only: true` + `cap_drop: [ALL]` + `tmpfs` — hardened.

---

## 4. Технологии по слоям

- **Frontend:** React 19, Vite 8, pnpm, **antd 6**, **echarts 6**, Redux Toolkit, react-router 7, i18next (ru/en).
- **API-шлюз:** YARP 2.3, .NET 10, самоподписанный HTTPS.
- **app-service:** ASP.NET Core 10.0, Npgsql 10, Novell.Directory.Ldap (LDAP/LDAPS), QuestPDF (отчёты), JWT.
- **ML:** Python 3.11, FastAPI, Uvicorn, Pydantic, **LightGBM 4.7**, pandas, NumPy, **PyArrow**, scikit-learn, joblib. Формат данных — **Parquet**. 4 модели (195–198 фич, temp-split: train <2026 / test 2026), реестр моделей, атомарные записи.
- **Broker:** asyncio, asyncpg, httpx, structlog, собственный cron-парсер (без apscheduler).
- **БД:** PostgreSQL (18 dev / 15 deploy), SQL-мigrations (001–040), `app_db`.
- **Auth:** Samba AD DC (домен `lct.ru`), LDAP/LDAPS, JWT.
- **CI/CD:** GitHub Actions (5 workflow: `ci.yml`, `publish-images.yml`, `deploy.yml`, `dashboard.yml`, `ml-broker-ci.yml`); **GHCR** как image-registry, immutable-теги `sha-<commit>`; SSH-deploy на сервер; smoke-тесты 5 сервисов в Docker-образе.
- **Observability:** OpenTelemetry Collector 0.128, Tempo 2.8.2 (traces), Loki 3.4.2 + Promtail (logs), Prometheus 2.54.1, Grafana 11.6.0, node-exporter 1.8.2.
- **Данные:** Parquet-артефакты, события 2019–2026, агрегаты (день/час), weather (Open-Meteo).

---

## 5. ML-модели и метрики (последние, 2026-09)

| Категория | AUC | Precision | Recall | Threshold |
|-----------|-----|-----------|--------|-----------|
| sensor-failure | **0.9687** | 0.9661 | 0.9532 | 0.22 |
| unauthorized-access | **0.9065** | 0.9241 | 0.9664 | 0.425 |
| infrastructure-wear | **0.8031** | 0.7856 | — | 0.5 |
| fire-risk | **0.5646** | 0.397 | 0.501 | 0.575 |

**Самая зрелая — sensor-failure (0.97 AUC).** fire-risk — самая слабая (label = transition, AUC 0.56).

---

## 6. Известные проблемы / расхождения

| # | Проблема | Источник |
|---|----------|----------|
| 1 | В **`README.md`** и **`web-frontend/README.md`** написано «Vue 3», а реальный стек — **React 19** (`package.json`, `src/main.jsx`) | Реальная проверка `package.json` |
| 2 | **`ml-data/extracted/`** (сырые CSV) на этой машине **потеряны** — агрегаты теперь append-only, пересборку из нуля нельзя | Проверка каталога |
| 3 | `fire-risk` AUC 0.56 — не проходит gate от roadmap (>= 0.75) | Skill `lct-product-roadmap` |
| 4 | 3 модели — реальные (LightGBM), но в roadmap от 2026-09-22 указано 3 из 4 как «synthetic baselines» — **статус устарел**: на 2026-09-29 все 4 trained на Parquet | Сравнение skill → реальные `models/*/meta.json` |

---

## 7. Итог
ЛCT — полноценный **microservice-стек** (13 компонентов) с:
- React-фронтендом и .NET API-шлюзом
- 2 Python ML-сервисами (ml-service + ml-broker) и 1 data-prep контейнером
- PostgreSQL + Samba AD
- Полным observability-стеком (OTel/Grafana/Tempo)
- GitHub Actions CI/CD с деплоем на сервер через SSH

**Вердикт:** зрелый production-ready проект с единственной критической проблемой — **расхождение в документации (Vue vs React)** и **потеря сырых данных** (append-only агрегаты).