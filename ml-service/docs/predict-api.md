# Контракт `POST /predict` — что подавать и что получаем

Базовый URL: `http://<host>:<port>` (сервер: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port <port>`).
Поля в JSON — **snake_case** (`category`, `subject_id`), не camelCase.

## Запрос

```json
{
  "category": "sensor-failure",
  "subject_id": "103904",
  "current_features": {},
  "horizon_hours": 24
}
```

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `category` | string | да | Один из: `sensor-failure`, `fire-risk`, `unauthorized-access`, `infrastructure-wear` |
| `subject_id` | string | да | Строковый id канала из данных (колонка `channel` в features-паркете, например `"103904"`) |
| `current_features` | object | нет (по умолчанию `{}`) | Свежий вектор фич на момент запроса. Ключи — имена фич категории (197 для `sensor-failure` / `unauthorized-access` / `infrastructure-wear`, 198 для `fire-risk`). Любые поданные ключи **переопределяют** значения, которые сервер посчитал из истории; отсутствующие базовые фичи сервер дополняет `0.0`. |
| `horizon_hours` | int | нет (по умолчанию 24, диапазон 1–168) | Формальное поле ответа (горизонт прогноза). Модель предсказывает «задуманное на ближайшие сутки» — значение на результат сейчас не влияет, но проходит в ответ. |

### Типичные варианты запроса

**Минимальный (история целиком с сервера):**
```json
{"category": "sensor-failure", "subject_id": "103904"}
```
Сервер сам берёт 11 lag-фич из накопленной истории канала (`lag_store`) и последнюю наблюдённую строку фич канала; чего нет — `0.0`.

**С обновлением «в реальном времени»:**
```json
{
  "category": "sensor-failure",
  "subject_id": "103904",
  "current_features": {"e7": 3, "a7": 1, "t7_0": 0.0, "since_alar": 0.0}
}
```
Эти 4 фичи заменяют серверные значения, остальные — из истории/ноль.

**Неизвестный канал:** ответ 200, lag-фичи = NaN-вектор (LightGBM понимает NaN нативно), базовые фичи = 0. Риск — «типичный по нулям», проверяйте по `model_version`, что модель вернулась.

## Ответ

`200 OK`:
```json
{
  "category": "sensor-failure",
  "subject_id": "103904",
  "risk_score": 0.83,
  "probability": 0.83,
  "predicted_label": true,
  "horizon_hours": 24,
  "predicted_at": "2026-09-20T15:04:11Z",
  "model_version": "v-20260920-143012",
  "feature_importance": {"e7": 3.0, "t7_0": 0.0, "...": 0.0}
}
```

| Поле | Описание |
|---|---|
| `risk_score` | P(событие в горизонт), 0.0–1.0 — главная выходная величина (калибруется изотонической калибровкой, если она сохранена в модели) |
| `probability` | Сырой выход модели (LightGBM: P(fail)) до калибровки — **именно на этой шкале выбирается порог** |
| `predicted_label` | bool: `probability` ≥ порога категории. Порог берётся из `models/<cat>/meta.json` `threshold` (по умолчанию 0.5) и подбирается как argmax F1 на валидации 2025. На последнем переобучении: `sensor-failure` 0.27, `unauthorized-access` 0.65, `fire-risk` 0.551, `infrastructure-wear` 0.5 |
| `horizon_hours` | Эхо запроса |
| `predicted_at` | Метка времени предсказания (UTC) |
| `model_version` | Версия использованной модели (сверить с `models/<cat>/meta.json`) |
| `feature_importance` | Не важность, а ИМЕНОВАННЫЙ вектор фич, на котором считалось предсказание (`имя фичи → значение`, все фичи категории). Для реальных моделей — 197/198 ключей |

## `POST /predict_all` — все 4 категории по одному каналу

```json
{"subject_id": "103904", "current_features": {}, "horizon_hours": 24}
```
Ответ: список ровно из 4 записей в порядке `sensor-failure`, `fire-risk`, `unauthorized-access`, `infrastructure-wear`:
```json
{
  "subject_id": "103904",
  "horizon_hours": 24,
  "predictions": [
    {"category": "sensor-failure", "applicable": true,  "prediction": {"risk_score": 0.13, "...": "..."}},
    {"category": "fire-risk",      "applicable": false, "prediction": null},
    {"category": "unauthorized-access", "applicable": false, "prediction": null},
    {"category": "infrastructure-wear", "applicable": true,  "prediction": {"risk_score": 0.11, "...": "..."}}
  ]
}
```

### `applicable` — покрытие категории (важно)

Каждая модель обучалась только на каналах своей подсистемы, и эти подсистемы **не пересекаются**: `fire-risk` — 6830 каналов, `unauthorized-access` — 2209, `infrastructure-wear` — 2443, и все они целиком входят в 11 482 канала `sensor-failure`. Значит для конкретного канала применимы ровно **две** категории: `sensor-failure` и одна из трёх остальных.

| `applicable` | Что значит | Что делать читателю |
|---|---|---|
| `true` | Модель обучалась на этом канале, `prediction` заполнен | Читать `risk_score` |
| `false` | Категория этот канал никогда не видела (чужая подсистема или канала нет в истории) | `prediction` = `null`; **риск не читать**, трактовать как «прогноза по этой категории нет» |

Раньше при `applicable=false` отдавалась константа, посчитанная по нулевому вектору («уверенный» прогноз из ничего) — теперь это явный `null`. В `forecast_results` брокер пишет для таких пар `{"status_code": "unpredictable"}`.

`POST /predict_all_batch` — то же для списка каналов за один вызов:
```json
{"subject_ids": ["103904", "103905"], "current_features": {"103905": {"e7": 3}}, "horizon_hours": 24, "as_of": "2026-06-30T00:00:00Z"}
```
Ответ: по одной `AllCategoriesResponse` на каждый канал, в порядке запроса; `current_features` — пер-канальный (`{subject_id: {фича: значение}}`), `as_of` — один на весь батч. Результат побайтово совпадает с последовательными вызовами `/predict_all` на том же `as_of`.

`POST /predict` (одна категория) поля `applicable` не имеет и считает **всегда** — это осознанно, на него опирается одиночный путь брокера.

## Ошибки

| Код | Когда |
|---|---|
| 422 | Неправильный `category` / невалидные типы (Pydantic валидация), либо модель категории не обучена / не зарегистрирована (`KeyError` из движка) |

## Проверка перед запросом

```bash
curl -s http://127.0.0.1:8742/healthz   # {"status":"ok"}
curl -s http://127.0.0.1:8742/status    # models.<cat>.model_version + lags.<cat> (свежесть истории: n_channels, n_rows, max_day)
```
`lags.<cat>.max_day` — дата последней накопленной строки истории. ⚠️ Если `lags.<cat>.status` = `empty` (а `n_channels` = `null`) — сервис НЕ видит паркеты фич: все каналы уйдут как «неизвестные» (`applicable=false` / нулевой вектор). Это признак неверно смонтированных данных (`LCT_DATA_DIR`), а не «плохой модели».
