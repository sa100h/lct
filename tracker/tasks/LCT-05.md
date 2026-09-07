---
id: LCT-05; title: Миграции доменной схемы БД; column: Review; points: 3; assignee: Ildar; due: 2026-09-09; tags: backend;db
---
# LCT-05 — Миграции доменной схемы БД

Набор `002_lct_domain.sql` в `postgres-db/migrations/app_db/`: equipment, alarm_events, predictions, maintenance_requests + индексы по времени/оборудованию. Через `shared/DatabaseMigration/PostgresMigrator.cs` (idempotent) применяется автоматически при старте app-service. Чекать идемпотентность на пустой БД и на уже заполненной.

## Чек-лист
- [x] Миграции написаны
- [x] Idempotency на чистой и заполненной БД
- [x] Индексы под запросы дашборда
