# app-service — ASP.NET Core API

Бизнес-сервис: реестры оборудования, события (alarm_events), предикции,
заявки на обслуживание. Общается с PostgreSQL и ml-service.

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
  (монтируется в `/migrations`): `001_initialize.sql`, `002_lct_domain.sql`,
  `003_auth.sql` (таблицы `users` и `refresh_tokens`).
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
pwsh ./scripts/generate-jwt-keys.ps1   # один раз, если ключей ещё нет
$env:Jwt__PublicKeyPath = (Resolve-Path .keys/jwt-public.pem).Path
$env:Jwt__PrivateKeyPath = (Resolve-Path .keys/jwt-private.pem).Path
$env:Ad__Host = 'dc1.lct.ru'
$env:Ad__CertificatePath = 'путь-к-публичному-ldaps.pem'
$env:Ad__BindPassword = 'пароль-lct-app-bind'
dotnet run --project app-service
```

Для прямого запуска также нужна доступная `app_db` и корректная строка
`ConnectionStrings:AppDb`; в Compose пути ключей и БД задаются автоматически.
