export function requestStatusTagColor(status) {
  if (status === 'Новая') {
    return 'blue'
  }
  if (status === 'В работе') {
    return 'orange'
  }
  if (status === 'Закрыта') {
    return 'green'
  }
  return 'default'
}
