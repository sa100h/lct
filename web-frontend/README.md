# web-frontend — Vue 3 SPA

Фронтенд: дашборд, прогнозы, карта, история, заявки, настройки.

## Стек

Vue 3 + Vite + pnpm, Pinia/Redux Toolkit для state, i18n (ru/en в `src/i18n/locales/`).

## Структура

| Путь | Назначение |
|------|-----------|
| `src/main.jsx` | точка входа |
| `src/components/app/App.jsx` | корневой компонент |
| `src/components/appLayout/AppLayout.jsx` | каркас (sidebar + header) |
| `src/components/sidebar/Sidebar.jsx` | меню |
| `src/components/header/Header.jsx` | шапка |
| `src/components/pages/dashboard/Dashboard.jsx` | главный дашборд |
| `src/components/pages/prediction/Prediction.jsx` | страница прогноза |
| `src/components/pages/map/Map.jsx` | карта коллекторов |
| `src/components/pages/history/History.jsx` | история событий |
| `src/components/pages/notifications/Notifications.jsx` | уведомления |
| `src/components/pages/reports/Reports.jsx` | отчёты |
| `src/components/pages/settings/Settings.jsx` | настройки |
| `src/store/index.js`, `src/store/menuSlice.js` | state (Redux Toolkit) |

## API

Запросы идут на `/api/app/**` и `/api/ml/**` — api-proxy проксирует их на
app-service и ml-service соответственно (в dev-режиме Vite `proxy` на localhost).

## Сборка и запуск

```bash
pnpm install --frozen-lockfile
pnpm run dev        # http://localhost:5173
pnpm run build      # dist/ — в Docker собирается stage'ом api-proxy/frontend-build
```

Примечание: отдельно фронтенд контейнером не поднимается — собирается в образ
api-proxy (`/src/web-frontend` → `wwwroot`), и в продакшене раздаётся шлюзом.

## Связи

- → `api-proxy` (`/api/app/**`, `/api/ml/**`)
