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

function compareForecastValues(a, b) {
  const byValue = b.value - a.value
  if (byValue !== 0) {
    return byValue
  }
  const byChannel = String(a.channelId).localeCompare(String(b.channelId))
  if (byChannel !== 0) {
    return byChannel
  }
  return String(a.category).localeCompare(String(b.category))
}

export function formatForecastValueList(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return []
  }
  return [...values]
    .sort(compareForecastValues)
    .map((item) => ({
      ...item,
      displayValue: Number(item.value).toFixed(2),
    }))
}
