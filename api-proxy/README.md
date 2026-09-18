# api-proxy — API-шлюз (YARP)

Единственная точка входа в приложение. На базе YARP проксирует API и раздаёт
собранную статику фронтенда.

## Маршруты

| Паттерн | Куда |
|---------|------|
| `/api/app/**` | `http://app-service:8080/**` |
| `/api/ml/**` | `http://ml-service:8000/**` |
| `/` (остальное) | статика `wwwroot` (сборка web-frontend) |

Настройка: `appsettings.json` → секции `ReverseProxy.Routes` / `Clusters`.

## Dockerfile (многоэтапный)

| Stage | Назначение |
|-------|-----------|
| `frontend-build` | node:22 + corepack/pnpm → `pnpm run build` из `web-frontend/` |
| `build` | dotnet sdk:10.0 → `dotnet publish api-proxy` |
| `dev-certificate` | `dotnet dev-certs https` → self-signed пара |
| `runtime` | aspnet:10.0,.publish + `wwwroot` из frontend-build, USER `$APP_UID` |
| `local` | runtime + self-signed cert в `/https/` — для локального Compose |
| `final` | плейсхолдер для CI-сборки deploy-образа |

## Порты

| Порт | Назначение |
|------|------------|
| 8080 | HTTP (в продакшене — редирект на HTTPS) |
| 8443 | HTTPS |

В `docker-compose.yml` наружу маппятся 80/8443; в `docker-compose.deploy.yml` — 80/443
с реальными сертификатами из `CERTS_PATH` (`/https`, только чтение).

## Настройки (`.env`)

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `ASPNETCORE_ENVIRONMENT` | `Production` | |
| `API_PROXY_HTTP_PORT` | `80` | наружный HTTP-порт |
| `API_PROXY_HTTPS_PORT` | `443` | наружный HTTPS-порт |
| `CERTS_PATH` | `./certs` | каталог `fullchain.pem`/`privkey.pem` (deploy) |

## Наблюдательность

Подключён общий builder из `shared/` (OTLP → `otel-collector:4317`). В локальном
Compose `Observability__OtlpEndpoint=""` (выключено), в observability-профиле — вкл.

## Связи

- → `app-service:8080`, `ml-service:8000` (YARP)
- → `otel-collector:4317` (при включённом profile observability)
- статика — из stage `frontend-build` (каталог `web-frontend/`)
