---
id: LCT-09; title: CI: тесты + сборка образов; column: Backlog; points: 2; assignee: Ildar; due: 2026-09-12; tags: ci
---
# LCT-09 — CI: тесты + сборка образов

`.github/workflows/ci.yml`: тесты (app-service.Tests, ml-service/tests, oxlint+eslint для фронта), сборка Docker-образов для публичной проверки. Не убить quick demo: таймауты и кэши.

## Чек-лист
- [ ] Тесты проходят в CI
- [ ] Docker-сборка всех сервисов
- [ ] Кэши npm/pip/dotnet
