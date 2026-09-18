# app-service — ASP.NET Core API

Бизнес-сервис: реестры оборудования, события (alarm_events), предикции,
заявки на обслуживание. Общается с PostgreSQL и ml-service.

## Структура

| Путь | Назначение |
|------|-----------|
| `Controllers/` | MVC-контроллеры для авторизации, статуса, прогноза и примера permission policy |
| `Contracts/` | API DTO для авторизации, статуса и прогнозов |
| `Services/Domain/` | сценарии авторизации, роли, permissions и интерфейсы портов |
| `Services/` | JWT, заглушка AD и HTTP-клиент ml-service |
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
| `Ad__Host`, `Ad__CertificatePath` | Compose | параметры будущего LDAPS адаптера |
| `AdGroups:*` | `appsettings.json` | соответствие AD групп четырём ролям |

## Порты

`8080` — внутренний, наружу выходит только через api-proxy (`/api/app/**`).

## Авторизация

`POST /auth/login`, `/auth/refresh`, `/auth/logout` работают с access JWT на
5 минут и одноразовым refresh в `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
Пока LDAP адаптер не реализован, login и refresh не выдают токены и отвечают
`503`. Для последующей интеграции предусмотрен интерфейс `IAdIdentityProvider`.

Роли и permissions задаются в `Services/Domain/RoleCatalog.cs`. Пока там только
демонстрационное `demo.access` для всех четырёх ролей. Его использование видно
на `GET /authz/demo`; бизнес матрицу следует заполнить до защиты реальных
ручек отдельными permissions. `IDistrictResourceAccess<TResource>` — контракт
для последующей проверки доступа диспетчера к району.

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
dotnet run --project app-service
```

Для прямого запуска также нужна доступная `app_db` и корректная строка
`ConnectionStrings:AppDb`; в Compose пути ключей и БД задаются автоматически.
