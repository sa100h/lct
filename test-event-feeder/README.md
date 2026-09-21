# test-event-feeder

Эмулятор внешнего журнала событий. При первом старте контейнер потоково читает
`ext-journal-2026.7z`, раскладывает записи по дневным CSV в именованном Docker
volume и затем проигрывает журнал в реальном времени.

Исходный момент `FEED_SOURCE_START_AT` отображается на момент готовности feeder.
После окончания архива новые события не выдаются. Исходные ID событий не меняются.

## Настройки

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `FEED_SOURCE_START_AT` | `2026-01-01T00:00:00` | Первая проигрываемая точка журнала |
| `FEED_TIME_ZONE` | `Europe/Moscow` | Часовой пояс исходных дат |
| `FEED_ARCHIVE_PATH` | `/data/ext-journal-2026.7z` | Смонтированный архив |
| `FEED_CACHE_DIRECTORY` | `/cache` | Постоянный подготовленный кэш |

## API

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/events?from=<ISO-8601>&to=<ISO-8601>&limit=1000&cursor=<optional>`

Диапазон событий полуоткрытый: `from <= occurredAt < to`. Время API всегда
должно содержать UTC offset. Ответ стабильно сортируется по `(occurredAt, id)`.

## Запуск

Положить `ext-journal-2026.7z` в корень репозитория и выполнить:

```bash
docker compose up --build test-event-feeder app-service
```

Первичная подготовка архива может занять несколько минут. Результат сохраняется
в volume `event_feed_cache`; последующие запуски используют готовый кэш.

Для повторной подготовки после замены архива следует удалить только этот volume:

```bash
docker compose down
docker volume rm lct_event_feed_cache
```
