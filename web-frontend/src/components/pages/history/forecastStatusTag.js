export const FORECAST_STATUS_LABEL = {
  pending: 'Ожидание',
  running: 'В работе',
  done: 'Готово',
  error: 'Ошибка',
  cancelled: 'Отменён',
  approved: 'Обработан',
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
  if (status === 'error') {
    return 'red'
  }
  if (status === 'cancelled') {
    return 'default'
  }
  if (status === 'approved') {
    return 'cyan'
  }
  return 'default'
}
