export function formatForecastStartedMessage(createdAt) {
  const formatted = new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(createdAt))
  return `Прогноз запущен в ${formatted}, ожидайте завершения`
}

export function forecastErrorMessage(status, body) {
  if (status === 403) {
    return 'Нет права запускать прогноз'
  }
  if (status === 400 && body && typeof body.error === 'string' && body.error) {
    return body.error
  }
  return 'Не удалось запустить прогноз'
}
