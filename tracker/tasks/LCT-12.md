---
id: LCT-12; title: README/доска: синхронизация; column: Backlog; points: 1; assignee: artaktavi; due: 2026-09-08; tags: docs
---
# LCT-12 — README/доска: синхронизация

README репозитория держит канбан-сводку и burndown (автогенерация из `tracker/`). Правило: сменил статус задачи → `gen_dashboard.py` → коммит. Workflow `dashboard.yml` делает это автоматически на main.

## Чек-лист
- [x] генератор написан
- [x] workflow настроен
- [ ] Проверяем автообновление на PR
