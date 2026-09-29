# app-service HTTP API

Базовый URL сервиса: `http://localhost:8080` (напрямую) или через шлюз `api-proxy`: префикс `/api/app`.

| Клиент | Пример |
|---|---|
| Прямо в app-service | `POST /auth/login` |
| Через api-proxy | `POST /api/app/auth/login` |
| Vite `pnpm dev` (`:5173`) | `POST /api/app/auth/login` (proxy снимает `/api/app`) |

JSON: `Content-Type: application/json`, имена полей **camelCase**.

По умолчанию все эндпоинты требуют JWT (`Authorization: Bearer <accessToken>`), кроме явно анонимных. Access-токен живёт **5 минут**. Refresh — httpOnly-cookie `lct_refresh` (path `/api/app/auth`, `Secure`, `SameSite=Strict`).

Роли AD и права UI (`RoleAccess:Roles` в `appsettings.json`): у всех есть `demo.access`. Модули веба — `module.*`:

| Роль JWT | `module.*` |
|---|---|
| `admin` | dashboard, map, prediction, history, requests, reports |
| `technician` | dashboard, map, requests, reports |
| `dispatcher_ods` | dashboard, map, prediction, history, requests, reports |
| `dispatcher_district` | map, history, requests, reports |

В поле `login` — `sAMAccountName` без домена. Демо-учётки создаёт `ad/init/01-users-groups.sh` (стенд, не для продакшена):

| Логин | Пароль | Группа AD | Роль JWT |
|---|---|---|---|
| `admin.test` | `Adm1n-test-2026` | Admins | `admin` |
| `technik.test` | `Tech1-2026` | Technics | `technician` |
| `dispetcher_ods` | `D1sp-2026` | Dispetchers_ODS | `dispatcher_ods` |
| `dispetcher_rayon` | `D1sp-ray-2026` | Dispetchers_rayon | `dispatcher_district` |

`lct-app-bind` — служебная учётка app-service для LDAP, в форму логина не подходит.

---

## Аутентификация

### `POST /auth/login`

Анонимно. Логин в AD, выдача access JWT и refresh-cookie.

**Тело**

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `login` | string | да | Учётная запись AD |
| `password` | string | да | Пароль |

**Ответ 200**

```json
{
  "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

Set-Cookie: `lct_refresh=<token>; HttpOnly; Secure; SameSite=Strict; Path=/api/app/auth`.

Access JWT (полезная нагрузка): `sub` (user id), `sid` (семья сессии), `role`, `login` (sAMAccountName), `permissions` (массив строк), `jti`, `iat`, `iss`, `aud`, `exp`.

**Пример**

```bash
curl -k -X POST https://localhost/api/app/auth/login \
  -H 'Content-Type: application/json' \
  -c cookies.txt \
  -d '{"login":"admin.test","password":"Adm1n-test-2026"}'
```

| Код | Когда |
|---|---|
| 400 | Пустые `login` / `password` (валидация) |
| 401 | Неверный логин или пароль |
| 403 | Учётная запись неактивна или нет роли в матрице |
| 503 | AD недоступен |

Пример 401 (ProblemDetails):

```json
{
  "type": "https://tools.ietf.org/html/rfc9110#section-15.5.2",
  "title": "Unauthorized",
  "status": 401
}
```

Пример 400:

```json
{
  "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
  "title": "One or more validation errors occurred.",
  "status": 400,
  "errors": {
    "Login": ["The Login field is required."],
    "Password": ["The Password field is required."]
  }
}
```

---

### `POST /auth/refresh`

Анонимно. Тело не нужно. Берёт refresh из cookie `lct_refresh`, ротирует его, возвращает новый access.

**Пример**

```bash
curl -k -X POST https://localhost/api/app/auth/refresh \
  -b cookies.txt \
  -c cookies.txt
```

**Ответ 200** — как у login (`accessToken` + новая cookie).

| Код | Когда |
|---|---|
| 401 | Нет cookie, битый/просроченный/уже использованный refresh |
| 403 | Пользователь деактивирован в AD |
| 503 | AD недоступен |

---

### `POST /auth/logout`

Анонимно. Отзывает refresh-семью (если cookie есть) и удаляет cookie.

**Пример**

```bash
curl -k -X POST https://localhost/api/app/auth/logout \
  -b cookies.txt \
  -c cookies.txt
```

**Ответ 204** — пустое тело.

---

## Статус сервиса

### `GET /status`

Анонимно. Живость app-service, без проверки БД и ML.

**Ответ 200**

```json
{
  "service": "app-service",
  "status": "ready"
}
```

**Пример**

```bash
curl -k https://localhost/api/app/status
```

---

### `GET /health`

Анонимно (общая обвязка observability). Health checks, в том числе PostgreSQL.

**Пример**

```bash
curl http://localhost:8080/health
```

Ожидается `Healthy` / соответствующий JSON health-check. Через api-proxy путь может быть недоступен (проксируется только `/api/app/*`).

### `GET /metrics`

Анонимно. Prometheus-метрики. Напрямую: `http://localhost:8080/metrics`.

---

## Диспетчерские объекты

### `GET /dispatcher_objects`

Нужны JWT и permission `module.map`. Возвращает все диспетчерские объекты с
расшифрованным типом, координатами WGS 84 и агрегированными статусами каналов.
Для каждого объекта `statuses` и `channelCount` учитывают его собственные
каналы и каналы всех вложенных объектов на любом уровне иерархии.
`ownStatuses` и `ownChannelCount` считают только каналы с
`dispatcher_object_id` этого объекта, без потомков.

**Ответ 200**

```json
[
  {
    "id": 5,
    "parentId": 5773,
    "name": "объект Альфа",
    "objectTypeId": 2,
    "objectTypeName": "controlHouse",
    "longitude": 37.5,
    "latitude": 55.61,
    "statuses": ["Норма"],
    "channelCount": 42,
    "ownStatuses": ["Норма"],
    "ownChannelCount": 3
  }
]
```

Объект без связанных каналов получает пустой массив `statuses` и
`channelCount: 0`. Объект без собственных каналов получает пустой массив
`ownStatuses` и `ownChannelCount: 0`.

---

## Дашборд

### `GET /dashboard`

Нужны JWT и permission `module.dashboard`. Одна сводка для экрана «Дашборд»:
цифры по объектам и агрегаты за 14 календарных дней UTC (включая сегодня).
Таблиц событий и прогнозов в ответе нет. Список заявок — в модуле
`GET /requests`; на дашборде заявки только как counts **по всем** строкам,
без фильтра роли.

**Ответ 200**

```json
{
  "objects": {
    "total": 80,
    "normal": 72,
    "deviation": 8
  },
  "alarmsByDay": [{ "date": "2026-09-15", "count": 3 }],
  "requestsTotal": 12,
  "requestsByStatus": [
    { "status": "Новая", "count": 4 },
    { "status": "В работе", "count": 5 },
    { "status": "Закрыта", "count": 3 }
  ],
  "requestsByDay": [{ "date": "2026-09-15", "count": 1 }],
  "forecastsByStatus": [
    { "status": "pending", "count": 2 },
    { "status": "running", "count": 0 },
    { "status": "done", "count": 6 }
  ]
}
```

Объект **в норме**, если `statuses` пустой или все значения равны `Норма`.
**Отклонение** — есть статус ≠ `Норма`.

Ряды `alarmsByDay` и `requestsByDay` всегда длины 14; дни без данных —
`count: 0`. `date` — `yyyy-MM-dd` UTC. Тревоги: `events_log.is_alarm`.
Заявки по дням: `requests.created_at`. `requestsByStatus` — три имени из
`request_statuses` (нули допустимы). `requestsTotal` — сумма этих трёх.
`forecastsByStatus` — итог за те же 14 дней по `forecast_journal.creation_time`,
не ряд по дням; три ключа `pending` / `running` / `done` (нули допустимы).

Статус прогноза: `pending` (нет start/end composition), `running` (есть start, нет end), `done` (есть end).

**Пример**

```bash
curl -k https://localhost/api/app/dashboard \
  -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
```

| Код | Когда |
|---|---|
| 401 | Нет или невалидный JWT |
| 403 | Нет права `module.dashboard` |

---

## Отчеты

### `GET /reports/{code}`

Нужны JWT и permission `module.reports`. PDF за период. Данные по всей системе,
без фильтра роли. `from` и `to` — календарные даты Москвы (`yyyy-MM-dd`), обе
включительно. Максимум 93 дня: `(to - from).Days + 1 ≤ 93`. В SQL — полуинтервал
UTC `[from 00:00 Europe/Moscow, (to+1 день) 00:00 Europe/Moscow)`.
`forecast_journal.creation_time` без пояса трактовать как UTC.

Коды: `summary`, `alarms`, `requests`, `technicians`, `forecasts`.
Имена файлов: `svodka_`, `trevogi_`, `zayavki_`, `tehniki_`, `prognozy_`
+ `{from}_{to}.pdf`.

Сводка: KPI тревог, заявок (созданных в периоде, текущий статус), прогнозов;
ряды по московским дням. Тревоги и заявки — таблицы до 2000 строк, иначе
«показано 2000 из N». Техники: создано в периоде; закрыто = статус «Закрыта» и
`updated_at` в периоде. Прогнозы: журналы за период, высокий риск как в истории
(порог `Forecast:RiskThreshold`).

Ответ 200: `application/pdf`. Пустые данные — всё равно PDF, не 404.

| Код | Когда |
|---|---|
| 400 | Нет/битые даты, `from > to`, больше 93 дней |
| 401 | Нет JWT |
| 403 | Нет `module.reports` |
| 404 | Неизвестный `code` |
| 500 | Сбой БД или рендера |

---

## Запуски прогнозирования

### `POST /forecasts/run`

Нужны JWT и permission `module.prediction`. Создаёт запись `manual` в `forecast_journal`.
Выбранные объекты разворачиваются в каналы, включая каналы дочерних объектов.
Для каждого канала в `forecast_channels` записывается последнее ненулевое текстовое
`sensor_value` из `events_log` за 24 часа до запуска либо `"Нет связи"`, если показаний
не было. Эндпоинт не вызывает ML-сервис. Значения
`start_composition_time` и `end_composition_time` остаются `NULL`.

**Тело**

```json
{
  "dispatcherObjectIds": [20, 111]
}
```

`dispatcherObjectIds: null` означает запуск для всех диспетчерских объектов.
Пустой массив, неизвестные идентификаторы и отсутствие показаний за 24 часа
возвращают `400 Bad Request` без создания записи журнала.
Повторяющиеся идентификаторы удаляются, итоговый список сортируется.

**Ответ 202**

```json
{
  "forecastJournalId": "2c059017-47c7-480a-b0a1-516be249695d",
  "status": "pending",
  "createdAt": "2026-09-25T10:30:00Z",
  "dispatcherObjectIds": [20, 111]
}
```

ID создателя берётся из `sub` текущего JWT. В `forecast_channels` сохраняется
JSONB-объект вида `{"120578":"23.5","120579":"Нет связи"}`. Ключ —
`sensor_channels.id`, значение — текст из `events_log.sensor_value` или `"Нет связи"`.
При автоматическом запуске `user_created_id` равен UUID служебного пользователя
`auto_forecast`, а `run_type` равен `auto`. `app-service` раз в час создаёт запись
для всех каналов. Если за 24 часа ни по одному каналу нет показаний, запись не
создаётся, а ошибка фиксируется в логе.
В том же проходе каналы без показаний получают статус «Нет связи», остальные — «Норма».

### `GET /forecasts/authors`

Нужны JWT и permission `module.history`. Логины пользователей, у которых есть хотя бы одна запись в `forecast_journal`, по возрастанию `login`.

**Ответ 200**

```json
[{ "id": "03863c40-04e4-4ffe-b7cf-3dd31dab0ade", "login": "admin.test" }]
```

Объявлять этот маршрут до `GET /forecasts/{id}`.

### `GET /forecasts`

Нужны JWT и permission `module.history`. Страница журнала запусков.

Query:

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `createdBy` | uuid | — | Автор запуска |
| `from` | `YYYY-MM-DD` | — | Дата создания, включительно |
| `to` | `YYYY-MM-DD` | — | Дата создания, включительно |
| `page` | int | 1 | Номер страницы |
| `pageSize` | int | 20 | Размер; больше 20 обрезается до 20 |

`page < 1` или `pageSize < 1`, битый uuid/дата — `400`. Сортировка: `creation_time DESC`, `id DESC`.

Статус: `pending` / `running` / `done` (как на дашборде). `objectCount` — число уникальных объектов, которым принадлежат каналы из `forecast_channels`. Для автоматической записи `authorLogin` равен `auto_forecast`.

**Ответ 200**

```json
{
  "items": [
    {
      "id": "2c059017-47c7-480a-b0a1-516be249695d",
      "createdAt": "2026-09-25T10:30:00Z",
      "authorLogin": "admin.test",
      "status": "pending",
      "objectCount": 96
    }
  ],
  "total": 1
}
```

### `GET /forecasts/{id}`

Нужны JWT и permission `module.history`. Деталь запуска: объекты с координатами,
оценкой и числами каналов.

- `hasResult` — есть строка `forecast_results` для объекта.
- `forecastValues` — только каналы с числом `value`. `unpredictable` и записи без
  числа не входят.
- `hasHighRisk`: без строки или без чисел → `null`; иначе `true`, если хотя бы
  одно `value` ≥ `Forecast:RiskThreshold` (по умолчанию `0.5`, env
  `Forecast__RiskThreshold`), иначе `false`.
- `isErroneous` — `forecast_results.is_erroneous`; нет строки → `false`. Если
  `isErroneous` true, `hasHighRisk` всегда `false`. `forecastValues` всё равно
  отдаём, если есть числа.

Поля в JSON не опускаются.

Список объектов строится по каналам из `forecast_channels` и включает их объекты-предки,
чтобы сохранить дерево истории.

**Ответ 200**

```json
{
  "id": "2c059017-47c7-480a-b0a1-516be249695d",
  "createdAt": "2026-09-25T10:30:00Z",
  "authorLogin": "admin.test",
  "status": "pending",
  "objects": [
    {
      "id": 20,
      "name": "объект Альфа",
      "parentId": null,
      "latitude": 55.6,
      "longitude": 37.45,
      "statuses": [],
      "hasHighRisk": null,
      "ownStatuses": ["Норма"],
      "ownChannelCount": 3,
      "isErroneous": false,
      "hasResult": false,
      "forecastValues": []
    },
    {
      "id": 5122,
      "name": "ДУ",
      "parentId": 20,
      "latitude": 55.62,
      "longitude": 37.51,
      "statuses": [],
      "hasHighRisk": false,
      "ownStatuses": ["Норма"],
      "ownChannelCount": 1,
      "isErroneous": true,
      "hasResult": true,
      "forecastValues": [
        { "channelId": "120578", "category": "fire-risk", "value": 0.81 }
      ]
    }
  ]
}
```

| Код | Когда |
|---|---|
| 401 | Нет JWT |
| 403 | Нет права `module.history` |
| 404 | Нет журнала |

### `POST /forecasts/{id}/erroneous`

Нужны JWT и permission `module.history`. Помечает выбранный объект и всех потомков как ошибочные (`forecast_results.is_erroneous`). Статус журнала не меняется. Повтор идемпотентен.

**Тело**

```json
{ "dispatcherObjectId": 5 }
```

**Ответ 204** без тела.

| Код | Когда |
|---|---|
| 400 | Объект не найден |
| 401 | Нет JWT |
| 403 | Нет `module.history` |
| 404 | Журнала нет |

---

## Пользователи и заявки

### `GET /users`

Нужны JWT и permission `module.requests`. Активные пользователи с ролью из таблицы `roles`. Пример: `?role=Technics`.

**Ответ 200**

```json
[{ "id": "03863c40-04e4-4ffe-b7cf-3dd31dab0ade", "login": "technik.test" }]
```

### `POST /requests`

Нужны JWT и permission `module.requests`. Создаёт заявку на журнал прогноза: выбранный объект и все потомки. Диспетчер — `sub` JWT. Статус «Новая».

**Тело**

```json
{
  "forecastJournalId": "2c059017-47c7-480a-b0a1-516be249695d",
  "dispatcherObjectId": 5,
  "description": "Проверить канал",
  "priority": 1,
  "technicianId": "03863c40-04e4-4ffe-b7cf-3dd31dab0ade"
}
```

**Ответ 201**

```json
{ "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" }
```

| Код | Когда |
|---|---|
| 400 | Нет описания, техник не Technics, объект не найден |
| 401 | Нет JWT |
| 403 | Нет `module.requests` |
| 404 | Журнала нет |

### `GET /requests`

Нужны JWT и permission `module.requests`. Список заявок: `admin` и `dispatcher_ods` видят все, остальные — если `user_dispatcher_id` или `user_technician_id` равен `sub`. Пагинация: `page`, `pageSize` (макс. 20). `objectId` / `objectName` — первый элемент `dispatcher_objects_id`.

**Ответ 200**

```json
{
  "items": [
    {
      "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "createdAt": "2026-09-28T08:00:00Z",
      "description": "Проверить канал",
      "objectId": 5,
      "objectName": "объект Альфа",
      "status": "Новая",
      "dispatcherLogin": "dispetcher_ods",
      "technicianLogin": "technik.test"
    }
  ],
  "total": 1
}
```

### `GET /requests/{id}`

Нужны JWT и permission `module.requests`. Карточка: шапка и объекты заявки плюс предки для дерева. Чужая заявка (не создатель и не исполнитель, если роль не admin/ODS) — **404**, не 403.

**Ответ 200**

```json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "createdAt": "2026-09-28T08:00:00Z",
  "description": "Проверить канал",
  "status": "Новая",
  "dispatcherLogin": "dispetcher_ods",
  "technicianLogin": "technik.test",
  "priority": 1,
  "objectId": 5,
  "objectName": "объект Альфа",
  "objects": [
    {
      "id": 5,
      "parentId": 1,
      "name": "объект Альфа",
      "latitude": 55.61,
      "longitude": 37.5,
      "statuses": ["Норма"],
      "ownStatuses": ["Норма"],
      "ownChannelCount": 1
    }
  ]
}
```

### `PATCH /requests/{id}/status`

Нужны JWT и permission `module.requests`. Любой, кто видит заявку, может поставить любой из статусов: «Новая», «В работе», «Закрыта».

**Тело**

```json
{ "status": "В работе" }
```

**Ответ 204** без тела.

| Код | Когда |
|---|---|
| 400 | Неизвестное имя статуса (`Неизвестный статус.`) |
| 401 | Нет JWT |
| 403 | Нет `module.requests` |
| 404 | Заявки нет или она скрыта (`Заявка не найдена.`) |

---

## ML через app-service

### `GET /ml/status`

Анонимно. Проксирует статус FastAPI `ml-service`.

**Ответ 200**

```json
{
  "service": "ml-service",
  "state": "ready",
  "now": "2026-09-16T00:00:00Z",
  "models": {
    "fire-risk": {
      "category": "fire-risk",
      "state": "trained",
      "modelVersion": "v1",
      "trainedAt": null,
      "metrics": {
        "source": "synthetic-baseline",
        "n_samples": 2000
      }
    }
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `service` | string | Имя ML-сервиса |
| `state` | string | Состояние процесса |
| `now` | datetime | Время ответа ML |
| `models` | object | Статус по категориям |
| `models.*.category` | string | Категория |
| `models.*.state` | string | Например `trained` |
| `models.*.modelVersion` | string | Версия модели |
| `models.*.trainedAt` | datetime \| null | Когда обучена |
| `models.*.metrics` | object | Произвольные метрики |

**Пример**

```bash
curl -k https://localhost/api/app/ml/status
```

| Код | Когда |
|---|---|
| 502 | ml-service недоступен или ответил ошибкой |

```json
{
  "error": "ml-service /status failed (503)."
}
```

---

### `POST /predict`

Нужен JWT (без него **401**). Политика permission на эндпоинте не висит — достаточно валидной сессии.

Прогноз через ml-service. Категории: `sensor-failure`, `fire-risk`, `unauthorized-access`, `infrastructure-wear`.

**Тело**

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `category` | string | да | Одна из четырёх категорий |
| `subjectId` | string | да | Id субъекта (датчик / ячейка / шахта / люк) |
| `currentFeatures` | object\<string, number\> | нет | Вектор признаков; ключи — имена фич категории. По умолчанию `{}` |
| `horizonHours` | int | нет | Горизонт 1…168, по умолчанию **24** |

**Ответ 200**

| Поле | Тип | Описание |
|---|---|---|
| `category` | string | Категория |
| `subjectId` | string | Субъект |
| `riskScore` | number | P(событие в горизонте), 0…1 |
| `probability` | number | Сырой выход модели, 0…1 |
| `predictedLabel` | bool | Метка прогноза |
| `horizonHours` | int | Горизонт |
| `predictedAt` | datetime | Время прогноза |
| `modelVersion` | string | Версия модели |
| `featureImportance` | object \| null | Важность признаков |

```json
{
  "category": "fire-risk",
  "subjectId": "sensor-1",
  "riskScore": 0.8,
  "probability": 0.75,
  "predictedLabel": true,
  "horizonHours": 24,
  "predictedAt": "2026-09-16T00:00:00Z",
  "modelVersion": "v1",
  "featureImportance": {
    "temperature": 0.4
  }
}
```

**Пример**

```bash
curl -k -X POST https://localhost/api/app/predict \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...' \
  -d '{
    "category": "fire-risk",
    "subjectId": "sensor-1",
    "currentFeatures": { "temperature": 62.5, "smoke": 0.1 },
    "horizonHours": 24
  }'
```

| Код | Когда |
|---|---|
| 401 | Нет или невалидный JWT |
| 400 | Неизвестная `category` |
| 502 | Ошибка ml-service |

```json
{
  "error": "Unknown category 'other'. Expected one of: sensor-failure, fire-risk, unauthorized-access, infrastructure-wear."
}
```

---

## Авторизация (демо)

### `GET /authz/demo`

Нужны JWT **и** claim `permissions` со значением `demo.access`.

**Ответ 200**

```json
{
  "role": "technician",
  "permissions": ["demo.access", "module.dashboard", "module.map"]
}
```

**Пример**

```bash
curl -k https://localhost/api/app/authz/demo \
  -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
```

| Код | Когда |
|---|---|
| 401 | Нет JWT |
| 403 | Нет права `demo.access` или сессия отозвана (`sid`) |

Через api-proxy этот путь идёт под политикой Default: без Bearer шлюз может отсечь запрос раньше app-service.

---

## Сводка

| Метод | Путь сервиса | Через шлюз | Auth |
|---|---|---|---|
| POST | `/auth/login` | `/api/app/auth/login` | нет |
| POST | `/auth/refresh` | `/api/app/auth/refresh` | cookie refresh |
| POST | `/auth/logout` | `/api/app/auth/logout` | cookie refresh (опц.) |
| GET | `/status` | `/api/app/status` | нет |
| GET | `/dispatcher_objects` | `/api/app/dispatcher_objects` | Bearer + `module.map` |
| GET | `/dashboard` | `/api/app/dashboard` | Bearer + `module.dashboard` |
| GET | `/reports/{code}` | `/api/app/reports/{code}` | Bearer + `module.reports` |
| GET | `/ml/status` | `/api/app/ml/status` | нет |
| POST | `/forecasts/run` | `/api/app/forecasts/run` | Bearer + `module.prediction` |
| GET | `/forecasts/authors` | `/api/app/forecasts/authors` | Bearer + `module.history` |
| GET | `/forecasts` | `/api/app/forecasts` | Bearer + `module.history` |
| GET | `/forecasts/{id}` | `/api/app/forecasts/{id}` | Bearer + `module.history` |
| POST | `/forecasts/{id}/erroneous` | `/api/app/forecasts/{id}/erroneous` | Bearer + `module.history` |
| GET | `/users` | `/api/app/users` | Bearer + `module.requests` |
| POST | `/requests` | `/api/app/requests` | Bearer + `module.requests` |
| GET | `/requests` | `/api/app/requests` | Bearer + `module.requests` |
| GET | `/requests/{id}` | `/api/app/requests/{id}` | Bearer + `module.requests` |
| PATCH | `/requests/{id}/status` | `/api/app/requests/{id}/status` | Bearer + `module.requests` |
| POST | `/predict` | `/api/app/predict` | Bearer |
| GET | `/authz/demo` | `/api/app/authz/demo` | Bearer + `demo.access` |
| GET | `/health` | нет (напрямую :8080) | нет |
| GET | `/metrics` | нет (напрямую :8080) | нет |
