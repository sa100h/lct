---
id: LCT-03; title: Обучение и приёмка моделей; column: To Do; points: 5; assignee: sa100h; due: 2026-09-29; tags: ml
---
# LCT-03 — Обучение и приёмка моделей

Базовые `HistGradientBoostingClassifier` на категорию, артефакты в `models/<category>/` (том `ml_models`). Принять по метрикам организатора: Precision > 0.7, Recall > 0.5, горизонт ≥ 24 ч. Таблицу метрик печатает `scripts/evaluate.py`.

## Чек-лист
- [x] Пайплайн train.py + реестр моделей
- [ ] Прогон на всех выгрузках
- [ ] Таблица метрик → в demo
- [ ] Достичь порога Precision/Recall
