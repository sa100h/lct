export const FORECAST_CATEGORY_LABEL = {
  'sensor-failure': 'отказ датчика',
  'fire-risk': 'пожарный риск',
  'unauthorized-access': 'несанкционированный доступ',
  'infrastructure-wear': 'износ инфраструктуры',
}

export function forecastCategoryLabel(category) {
  return FORECAST_CATEGORY_LABEL[category] ?? category
}

export function forecastResultHeadline(object) {
  if (!object?.hasResult) {
    return 'Результатов прогноза пока нет'
  }
  const values = object.forecastValues ?? []
  if (values.length === 0) {
    return 'Нет оценки модели'
  }
  return object.hasHighRisk ? 'Высокий риск' : 'В норме'
}
