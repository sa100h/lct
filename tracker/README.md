# NicePlan — git-native трекер

Планирование в духе [GitScrum](https://docs.gitscrum.com/en) без отдельной
системы: всё живёт в репозитории, статус виден прямо в README.

> **Подробная инструкция: [`INSTRUCTIONS.md`](./INSTRUCTIONS.md)** — где
> backlog, как создавать и двигать задачи, спринт-планирование, правила.

## Модели GitScrum, которые мы используем
- **Kanban** — колонки `Backlog → To Do → In Progress → Review → Done`.
- **Спринт** — таймбокс с ёмкостью в story points (`tracker/config.toml`).
- **Задача** — markdown-файл: ID, title, points, assignee, due, tags + чек-лист.
- **Burndown** — факт vs идеальный курс, пересчитывается в README.

## Формат задачи
Файл `tracker/tasks/LCT-04.md`:

```markdown
---
id: LCT-04; title: Аналитика выгрузок; column: Backlog; points: 2; assignee: Ildar; due: 2026-09-11; tags: data;ml
---
# LCT-04 — Аналитика выгрузок

Текст задачи...

## Чек-лист
- [ ] шаг 1
- [ ] шаг 2
```

`column` — одна из: `Backlog`, `To Do`, `In Progress`, `Review`, `Done`.
Прочие поля: `points` (story points, 1/2/3/5/8…), `assignee` (git-login),
`due` (ISO-дата), `tags` (через `;`).

## Как двигать задачу
1. Отредактируйте `column` в `tracker/tasks/<ID>.md` (и чек-лист).
2. `python3 tracker/gen_dashboard.py` — пересоберёт канбан + burndown в README.
3. Коммит → push. На `main` workflow `dashboard.yml` делает шаги 2–3
   автоматически, если не забыли.

## Команды
- `python3 tracker/build_seed.py` — (пере)создаёт seed-задачи.
- `python3 tracker/gen_dashboard.py` — пересобирает дашборд в README.

## Спринт
Название, состояние, даты, ёмкость — в `[sprint]` в `tracker/config.toml`.
Когда спринт закрывается: `state = finished`, задайте новый спринт и
пересоберите. History спринтов — в `tracker/retro/` (добавляйте по желанию).
