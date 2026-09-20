# Как менять параметры обучения (LightGBM)

Действующий движок — LightGBM (`--engine lgbm` по умолчанию). Все пути — от каталога `ml-service/`.

## Что где лежит

| Параметр | Где | Текущее значение |
|---|---|---|
| Базовые гиперпараметры модели | `app/models/lgbm_model.py` → `LGB_PARAMS_DEFAULT` | `learning_rate=0.08`, `num_leaves=31`, `min_data_in_leaf=20`, `feature_fraction=0.9`, `bagging_fraction=0.9`, `bagging_freq=1` |
| Эпохи (раунды) | `app/models/lgbm_model.py` → `DEFAULT_ROUNDS`; фактически их подбирает early stopping | 300 (потолок), реальные — `booster.best_iteration` |
| Early stopping (терпение) | `scripts/train.py` → `fit_lgbm(..., early_stopping=50)` | 50 раундов без улучшения на valid |
| Размер обучающей выборки | `app/models/lgbm_model.py` → `MAX_TRAIN_ROWS` / `MAX_VALID_ROWS` | 1 000 000 / 500 000 |
| Гиперпараметры тюнинга | `scripts/tune_lgbm.py` → `TUNED`, `NUM_BOOST_ROUND`, `EARLY_STOP` | `num_leaves=63`, `max_depth=8`, `min_data_in_leaf=2000`, `feature_fraction=0.8`, `lr=0.05`, 1500 раундов, эстоп 100 |
| Горизонт ответа API | переменная окружения `ML_HORIZON_HOURS` | 24 |

## Справочник по изменению

**Эпохи (раунды бустинга).** LightGBM — это бустинг, «эпоха» = один раунд (оно дерево). Три сценария:
1. **Подбор через early stopping** (стандарт в `scripts.train`): модель тренируется до `rounds or 300` с `early_stopping=50` на valid=2025, затем финальный прогон с найденным `best_iteration` без эстопа. Чтобы изменить потолок — правьте число в `train_lgbm()` (`rounds=rounds or 300`) и `DEFAULT_ROUNDS`; «терпение» — `early_stopping=50` в том же файле.
2. **Фиксированное число раундов** — дайте `rounds` из тюнинга (`--tuned`), эстоп при финальном фите не включается.
3. **Своя команда** — `fit_lgbm(dataset, params={...}, rounds=N)` принимает любые раунды.

**Размер батча.** Классического batch size в LightGBM **нет** — это гистограммный градиентный бустинг, каждый раунд проходит по всей выборке. Аналогичные настройки, которые обычно трогают вместе с «батчем»:
- `bagging_fraction` / `bagging_freq` — доля строк и периодичность ресэмплинга (в `LGB_PARAMS_DEFAULT`: 0.9 / 1);
- `feature_fraction` — доля фич на дерево (0.9);
- `max_bin` (по умолчанию 255) — разрешение гистограмм; уменьшение экономит память, но тут мы и так ограничены `MAX_TRAIN_ROWS` под 3.8 GB.
Для смены реального объёма обучения — меняйте `MAX_TRAIN_ROWS`/`MAX_VALID_ROWS` в `lgbm_model.py` (на этой машине не поднимайте выше 1.0M без проверки RAM).

**Скорость обучения** — `learning_rate` (0.08). При снижении lr почти всегда надо увеличивать раунды (early stopping сам подберёт, но поднимите потолок).

**Глубина дерева** — `num_leaves` (31; в тюнинге 63) и опционально `max_depth` (в тюнинге 8). `num_leaves` — главный рычаг сложности.

**Минимум строк в листе** — `min_data_in_leaf` (20; в тюнинге 2000).

## Как применить изменения (production)

1. Правите нужные значения в файлах выше (или в `scripts/tune_lgbm.py`, если меняете сетку тюнинга).
2. Пробегаете Тюнинг: `.venv/bin/python -m scripts.tune_lgbm` — пишет `ml-data/lags/lgbm-tuned-results.json` (сетка сейчас фиксирована в `TUNED`; при необходимости расширьте словарь).
3. Финальное обучение: `.venv/bin/python -m scripts.train --tuned` (или без `--tuned`, если правили `LGB_PARAMS_DEFAULT` напрямую).
4. Проверка: `cat models/<cat>/meta.json` — сравните `auc`/`ap`/`precision`/`recall` и `final_rounds` с прошлыми запусками; метрики test=2026 не должны просесть.

Быстрый прогон одной категории: `.venv/bin/python -m scripts.train --category sensor-failure --tuned`.

## Откат

- `--engine hgb` — старый HistGradientBoosting (`app/models/baseline.py`), параметры там в `baseline.py`.
- `--no-lags <cat>` — обучение без 11 lag-фич для конкретной категории.
- Модели лежат в `models/<cat>/model.lgb` + `meta.json` (untracked, локально) — перед экспериментальным обучением скопируйте текущий `models/` в backup-папку.
