export const FORECAST_STATUS_LABEL = {
  pending: 'Ожидание',
  running: 'В работе',
  done: 'Готово',
}

export function forecastStatusTagColor(status) {
  if (status === 'pending') {
    return 'blue'
  }
  if (status === 'running') {
    return 'orange'
  }
  if (status === 'done') {
    return 'green'
  }
  return 'default'
}
