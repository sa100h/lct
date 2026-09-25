# app-service — ASP.NET Core API

Бизнес-сервис: реестры оборудования, события (alarm_events), предикции,
заявки на обслуживание. Общается с PostgreSQL и ml-service.

## Тестовый поток событий

При `EventFeed:Enabled=true` фоновый `EventFeedPollingWorker` каждые пять минут
запрашивает у `test-event-feeder` последние семь минут. Двухминутное перекрытие
устраняется в памяти по исходному ID события. События с известными каналами
идемпотентно записываются в `events_log` по исходному ID, после чего обработчик
пишет сводную информацию в лог. В `event_datetime` сохраняется `OccurredAt`
как `TIMESTAMPTZ`. События неизвестных `sensor_channels` пропускаются с одним
агрегированным предупреждением на пачку и считаются обработанными.

Настройки находятся в секции `EventFeed`: `BaseUrl`, `PollInterval`,
`RetryInterval`, `Lookback`, `PageSize` и `RequestTimeout`. Недоступность feeder
не останавливает приложение: worker логирует предупреждение и повторяет запрос
через `RetryInterval`; после успеха возвращается к обычному `PollInterval`.

## Структура

| Путь | Назначение |
|------|-----------|
| `Controllers/` | MVC-контроллеры для авторизации, статуса, прогноза и примера permission policy |
| `Contracts/` | API DTO для авторизации, статуса и прогнозов |
| `Services/Domain/` | сценарии авторизации, каталог доступа и интерфейсы портов |
| `Services/Infrastructure/` | LDAPS-клиент и проверка сертификата AD |
| `Services/` | JWT и HTTP-клиент ml-service |
| `Data/Repositories/` | Npgsql-репозиторий пользователей и refresh token |
| `Models/` | внутренние модели авторизации |
| `Extensions/` | регистрация зависимостей, политики доступа и запуск миграций |

## Данные

- БД: `app_db` на postgres:18. Пользователь `app_service` создаётся
  `postgres-db/init/02-init-create-user.sh`.
- Миграции применяются при старте контейнером из `./postgres-db/migrations`
  (монтируется в `/migrations`): последовательно от `001_initialize.sql` до
  `009_events_log_timestamp_with_time_zone.sql`; `003_auth.sql` создаёт таблицы
  `users` и `refresh_tokens`, а `006` и `009` — журнал событий и его временную
  семантику.
  Механика — `shared/DatabaseMigration/PostgresMigrator.cs`.

## Настройки

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `ConnectionStrings__AppDb` | — | Host=postgres;Database=app_db;Username=app_service |
| `Migrations__Path` | `/migrations/app_db` | каталог SQL-миграций |
| `MlService__BaseUrl` | `http://ml-service:8000` | адрес ML-сервиса |
| `Observability__OtlpEndpoint` | `""` | OTLP-коллектор |
| `Jwt:Issuer`, `Jwt:Audience` | `appsettings.json` | область доверия access JWT; proxy задаёт те же значения в своём `appsettings.json` |
| `Jwt__PrivateKeyPath`, `Jwt__PublicKeyPath` | Compose | приватный и публичный PEM ключи |
| `Ad__Host`, `Ad__CertificatePath` | Compose | имя LDAPS-сервера и публичный сертификат |
| `Ad__BindPassword` | `.env` через Compose | пароль `lct-app-bind` для чтения AD |
| `Ad:Port`, `Ad:BaseDn`, `Ad:BindName`, `Ad:TimeoutSeconds` | `appsettings.json` | параметры поиска и подключения к AD |
| `RoleAccess:Roles` | `appsettings.json` | единая матрица «DN группы AD → роль → permissions» |

## Порты

`8080` — внутренний, наружу выходит только через api-proxy (`/api/app/**`).

## Авторизация

`POST /auth/login`, `/auth/refresh`, `/auth/logout` работают с access JWT на
5 минут и одноразовым refresh в `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
Login принимает короткий `sAMAccountName` и проверяет пароль пользовательским
bind через LDAPS. Refresh читает состояние и группы по стабильному `objectGUID`
через сервисную учётную запись. `is_active` отражает флаг AD `ACCOUNTDISABLE`.
Если AD или проверка TLS недоступны, login/refresh возвращают `503`.

Единственный источник назначения ролей и permissions — `RoleAccess:Roles` в
`appsettings.json`. `PermissionCodes` содержит только имена permission policies
для атрибутов `[Authorize]`; сами политики регистрируются из матрицы при старте.
Этот класс не назначает права ролям. Сейчас всем четырём
ролям выдано только демонстрационное `demo.access` для `GET /authz/demo`.
При запуске сервис проверяет, что каждое право из `[Authorize(Policy = ...)]`
есть в матрице; ошибка конфигурации останавливает запуск с названием ручки.
Бизнес матрицу нужно заполнить до защиты реальных ручек отдельными permissions.
`IDistrictResourceAccess<TResource>` — контракт для последующей проверки
доступа диспетчера к району.

Приложение доверяет конкретному публичному сертификату из `Ad__CertificatePath`
и проверяет DNS-имя сервера. После перевыпуска сертификата AD перезапустите
`app-service`, чтобы он загрузил новую публичную часть.

## Связи

- ← `api-proxy` (`/api/app/**`)
- → `postgres:5432` (app_db)
- → `ml-service:8000` (`/predict`, `/status`)
- → `otel-collector:4317` (observability-профиль)

## Локальный запуск

```bash
./scripts/generate-jwt-keys.sh   # один раз, если ключей ещё нет
export Jwt__PublicKeyPath="$(realpath .keys/jwt-public.pem)"
export Jwt__PrivateKeyPath="$(realpath .keys/jwt-private.pem)"
export Ad__Host='dc1.lct.ru'
export Ad__CertificatePath='путь-к-публичному-ldaps.pem'
export Ad__BindPassword='пароль-lct-app-bind'
dotnet run --project app-service
```

Для прямого запуска также нужна доступная `app_db` и корректная строка
`ConnectionStrings:AppDb`; в Compose пути ключей и БД задаются автоматически.
