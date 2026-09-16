# Deployment

Pipeline сохраняет трехступенчатую схему: CI проверяет код и Dockerfile, `Publish Images` публикует выбранные образы в GHCR, `Deploy` устанавливает выбранные сервисы на сервер по SSH. Для первого запуска выберите все три сервиса (`api-proxy`, `app-service`, `ml-service`) и опубликуйте все три образа с одним тегом.

Сервисы наблюдаемости в `docker-compose.deploy.yml` находятся в профиле `observability` и при обычном деплое не запускаются. Логи приложений доступны через `docker compose logs`.

## GitHub secrets для environment

- `DEPLOY_HOST`
- `DEPLOY_PORT`
- `DEPLOY_USER`
- `DEPLOY_PATH`
- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_HEALTHCHECK_URL` — необязательный внешний URL проверки.

## Подготовка сервера

В `DEPLOY_PATH` должен находиться приватный `.env`, созданный по `.env.example`. В нем нужны только `POSTGRES_PASSWORD` и `APP_DB_PASSWORD`. Workflow не загружает секреты и не перезаписывает серверный `.env`. Реестр, namespace и теги образов он записывает в `.env.release` автоматически. При первом деплое нужно выбрать все три сервиса; при следующих деплоях теги невыбранных сервисов сохраняются.

Для HTTPS положите `fullchain.pem` и **незашифрованный** `privkey.pem` в каталог на сервере, указанный переменной `CERTS_PATH` в `.env`. По умолчанию это `DEPLOY_PATH/certs`. Docker монтирует этот каталог в `/https`; внутренние пути сертификата и ключа заданы в Compose. Доступ к приватному ключу должен быть у пользователя контейнера `api-proxy`. Пароль сертификата больше не нужен. Порты по умолчанию: HTTP 80 только для перенаправления, HTTPS 443 для всего приложения; при необходимости серверный `.env` может задать `API_PROXY_HTTP_PORT` и `API_PROXY_HTTPS_PORT`.

Рекомендуемый порядок: успешный `CI` для commit → `Publish Images` с immutable тегом `sha-<commit>` → `Deploy` с тем же тегом.

