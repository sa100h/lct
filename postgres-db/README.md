# postgres-db — PostgreSQL 18

Единственный источник данных приложения: `app_db` для app-service.

## Файлы

| Файл | Когда выполняется | Назначение |
|------|-------------------|-----------|
| `init/01-init.sql` | при первом старте (initdb) | создание базы `app_db` |
| `init/02-init-create-user.sh` | при первом старте | пользователь `app_service` с паролем из `APP_DB_PASSWORD` |
| `migrations/app_db/001_initialize.sql` | при каждом старте app-service | базовая схема |
| `migrations/app_db/002_lct_domain.sql` | при каждом старте app-service | доменная схема: equipment, alarm_events, predictions, maintenance_requests |

Скрипты из `init/` — штатный механизм Postgres (`/docker-entrypoint-initdb.d`),
срабатывают только при пустом volume. Миграции из `migrations/` применяются самим
app-service (`shared/DatabaseMigration/PostgresMigrator.cs`), idempotentно.

## Схемы

- **app_db**: `equipment`, `alarm_events`, `predictions`, `maintenance_requests`
  (создано миграцией `002_lct_domain.sql`).
- Диаграммы ER и ролей — в каталоге `docs/`.

## Настройки

| Переменная | Назначение |
|------------|-----------|
| `POSTGRES_PASSWORD` | пароль суперпользователя `postgres` |
| `APP_DB_PASSWORD` | пароль пользователя `app_service` |

## Порты / хранение

Внутренний `5432` на `app-network`. Данные — volume `postgres_data`.

## Связи

- ← `app-service` (`postgres:5432/app_db`)
- ← ml-service (при подключении к данным, если потребуется)

## Локальный доступ

```bash
docker compose exec postgres psql -U postgres -d app_db
```
