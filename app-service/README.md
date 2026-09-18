# app-service — ASP.NET Core API

Бизнес-сервис: реестры оборудования, события (alarm_events), предикции,
заявки на обслуживание. Общается с PostgreSQL и ml-service.

## Структура

| Путь | Назначение |
|------|-----------|
| `Program.cs` | composition root: DI, observability (shared), endpoints |
| `Ml/MlServiceClient.cs` | HTTP-клиент к ml-service (`/predict`, `/status`) |
| `Contracts/PredictionContracts.cs` | DTO прогнозов (совпадает со схемой ml-service) |
| `Contracts/ServiceStatusResponse.cs` | DTO статуса |
| `Tests/MlServiceClientTests.cs`, `Tests/StatusEndpointTests.cs` | unit-тесты (запускаются в CI) |

## Данные

- БД: `app_db` на postgres:18. Пользователь `app_service` создаётся
  `postgres-db/init/02-init-create-user.sh`.
- Миграции применяются при старте контейнером из `./postgres-db/migrations`
  (монтируется в `/migrations`): `001_initialize.sql`, `002_lct_domain.sql`
  (таблицы equipment, alarm_events, predictions, maintenance_requests).
  Механика — `shared/DatabaseMigration/PostgresMigrator.cs`.

## Настройки

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `ConnectionStrings__AppDb` | — | Host=postgres;Database=app_db;Username=app_service |
| `Migrations__Path` | `/migrations/app_db` | каталог SQL-миграций |
| `MlService__BaseUrl` | `http://ml-service:8000` | адрес ML-сервиса |
| `Observability__OtlpEndpoint` | `""` | OTLP-коллектор |

## Порты

`8080` — внутренний, наружу выходит только через api-proxy (`/api/app/**`).

## Связи

- ← `api-proxy` (`/api/app/**`)
- → `postgres:5432` (app_db)
- → `ml-service:8000` (`/predict`, `/status`)
- → `otel-collector:4317` (observability-профиль)

## Локальный запуск

```bash
dotnet run --project app-service   # MlService__BaseUrl=http://localhost:8000 по умолчанию
```
