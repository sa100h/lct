# postgres-db — PostgreSQL 18

Единственный источник данных приложения: `app_db` для app-service.

## Файлы

| Файл | Когда выполняется | Назначение |
|------|-------------------|-----------|
| `init/01-init.sql` | при первом старте (initdb) | создание базы `app_db` |
| `init/02-init-create-user.sh` | при первом старте | пользователь `app_service` с паролем из `APP_DB_PASSWORD` |
| `migrations/app_db/001_initialize.sql` | при каждом старте app-service | базовая схема |
| `migrations/app_db/002_lct_domain.sql` | при каждом старте app-service | доменная схема: equipment, alarms, predictions, maintenance_requests |
| `migrations/app_db/006_adding_default_tables.sql` | один раз через migrator | справочники датчиков и `events_log` |
| `migrations/app_db/009_events_log_timestamp_with_time_zone.sql` | один раз через migrator | перевод времени событий в `TIMESTAMPTZ` |

Скрипты из `init/` — штатный механизм Postgres (`/docker-entrypoint-initdb.d`),
срабатывают только при пустом volume. Миграции из `migrations/` применяются самим
app-service (`shared/DatabaseMigration/PostgresMigrator.cs`), idempotentно.

## Схемы

- **app_db**: бизнес-таблицы приложения, включая `equipment`, `alarms`,
  `events_log`, `predictions` и `maintenance_requests`.
- Диаграммы ER и ролей — в каталоге `docs/`.

## Настройки

| Переменная | Назначение |
|------------|------------|
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

## Тестовые справочники для event feeder

После запуска `postgres` можно заполнить справочники `engineering_systems`,
`sensor_types`, `object_types`, `dispatcher_objects`, `sensor_statuses` и
`sensor_channels` из CSV в `ml-data`:

```bash
python scripts/seed_event_feed_references.py --apply
```

Скрипт использует запущенный Compose-контейнер `postgres`, выполняет загрузку
одной транзакцией и при повторном запуске не перезаписывает существующие строки.
Без `--apply` он печатает SQL для просмотра. Это тестовая загрузка: координаты
объектов устанавливаются в `0`, всем каналам задаётся статус «Неизвестно (тест)»,
к одинаковым названиям добавляется ID, а для отсутствующего в CSV родителя
`3831` создаётся помеченный тестовый объект. На момент подготовки скрипта CSV
содержали 11 485 каналов. Ранее пропущенные worker-ом события загрузка
справочников сама по себе не восстанавливает.
