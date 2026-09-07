---
id: LCT-08; title: Наблюдаемость: метрики + дашборд; column: Backlog; points: 3; assignee: artaktavi; due: 2026-09-12; tags: ops
---
# LCT-08 — Наблюдаемость: метрики + дашборд

Prometheus `:9090`, Grafana `:3000`, Tempo `:3200`, Loki `:3100` уже в compose. Сделать: дашборд «Хакатон LCT» (QPS, латентность предиктов, свежие прогнозы, статусы моделей). Конфиги: `observability/`.

## Чек-лист
- [ ] Дашборд Grafana (JSON)
- [ ] Метрики ml-service (predict time, fallback)
- [ ] Трассировка браузер → api → ml
