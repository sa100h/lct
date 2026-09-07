---
id: LCT-01; title: Контракт ML API согласован; column: Done; points: 3; assignee: Ildar; due: 2026-09-08; tags: ml;backend
---
# LCT-01 — Контракт ML API согласован

FastAPI ml-service отвечает контракту: `POST /predict` (категория, признакный вектор → вероятность, интерпретация), `GET /status` (модели, метрики), `GET /healthz`. Схемы зафиксированы в `ml-service/app/schemas.py` и `app-service/Contracts/PredictionContracts.cs`, синхронизированы по обе стороны.

Решения: горизонт прогноза 24 ч; по одной модели на категорию; контракты — source of truth для фронтенда.

## Чек-лист
- [x] Описать Pydantic-схемы запроса/ответа
- [x] Отразить в C#-контрактах app-service
- [x] Понятить smoke-тест под контракт
