# observability — Grafana-стек (профиль `observability`)

Набор контейнеров для трейсов, логов и метрик — **опциональный профиль
`observability`**, нарезанный в `docker-compose.deploy.yml`. В локальном
`docker-compose.yml` эти сервисы закомментированы (по умолчанию не
поднимаются). Включается в deploy-стёке:

```bash
docker compose -f docker-compose.deploy.yml --profile observability up -d
```

## Контейнеры

| Сервис | Образ | Порт (наружу) | Назначение |
|--------|-------|---------------|------------|
| `otel-collector` | otel/opentelemetry-collector-contrib:0.128.0 | 4317 (внутр.) | приём OTLP, ротация: traces → Tempo, logs → Loki |
| `tempo` | grafana/tempo:2.8.2 | 3200 (внутр.) | хранение трейсов |
| `loki` | grafana/loki:3.4.2 | 3100 (внутр.) | хранение логов |
| `promtail` | grafana/promtail:3.4.2 | — | сбор docker-логов → Loki (монтирует `/var/run/docker.sock`) |
| `prometheus` | prom/prometheus:v2.54.1 | 9090 | метрики (scrape: node-exporter, app-service) |
| `grafana` | grafana/grafana:11.6.0 | 3000 | дашборды, датасорцы: Loki, Tempo, Prometheus |
| `node-exporter` | prom/node-exporter:v1.8.2 | 9100 (внутр.) | метрики хоста |

Конфиги каждого — в соответствующей подкаталогии (`loki/`, `tempo/`,
`otel-collector/`, `prometheus/`, `promtail/`, `grafana/provisioning/`).
JSON-дашборды кладут в `grafana/dashboards/` (автоматический provisioning).

## Настройки

| Переменная | По умолчанию | Назначение |
|------------|--------------|-----------|
| `PROMETHEUS_PORT` | `9090` | |
| `GRAFANA_PORT` | `3000` | |
| `GRAFANA_ADMIN_USER` | `admin` | |
| `GRAFANA_ADMIN_PASSWORD` | `change-me` | |
| `ASPNETCORE_ENVIRONMENT` | `Production` | promtail использует для тегов |

## Как включается OTLP в сервисах

`Observability__OtlpEndpoint` в `app-service`/`api-proxy` — в локальном
`docker-compose.yml` принудительно пустой (экспорт выключен). В deploy-стёке
с профилем `observability` ставится `http://otel-collector:4317`.

## Связи

- `app-service` / `api-proxy` → `otel-collector:4317` (gRPC OTLP)
- `otel-collector` → `tempo:3200` (traces), `loki:3100` (logs)
- `promtail` → `loki:3100`
- `prometheus` ← `node-exporter:9100`, `app-service`/`api-proxy` (metrics)
- `grafana` → loki/tempo/prometheus (datasources)
