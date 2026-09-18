# shared — общий C#-код

Общая C#-библиотека, которую используют и `api-proxy`, и `app-service` (общий
`shared.csproj`).

## Файлы

| Файл | Назначение |
|------|-----------|
| `DatabaseMigration/PostgresMigrator.cs` | идемпотентное применение SQL-миграций из каталога `Migrations__Path` |
| `Observability/ObservabilityOptions.cs` | биндинг секции `Observability` из appsettings |
| `Observability/SharedObservabilityBuilderExtensions.cs` | extension-method: OTLP-экспорт, traces, HttpClient tracing, EF tracing |
| `Observability/TraceContextEnricher.cs` | обогащение трейсов контекстом |

## Настройки

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `Observability__OtlpEndpoint` | `http://otel-collector:4317` | OTLP gRPC |
| `Observability__DefaultLogLevel` | `Information` | |
| `Observability__EnableAspNetCoreTracing` | `true` | |
| `Observability__EnableHttpClientTracing` | `true` | |
| `Observability__EnableEntityFrameworkCoreTracing` | `false` | |

В локальном Compose `OtlpEndpoint` принудительно пустой — экспорта нет, только логи.

## Связи

- ← `api-proxy` (csproj reference)
- ← `app-service` (csproj reference)
