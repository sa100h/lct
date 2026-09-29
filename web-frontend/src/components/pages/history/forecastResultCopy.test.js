import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  forecastCategoryLabel,
  forecastResultHeadline,
  formatForecastValueList,
} from './forecastResultCopy.js'

test('forecastResultHeadline when there is no result row', () => {
  assert.equal(forecastResultHeadline({ hasResult: false }), 'Результатов прогноза пока нет')
  assert.equal(forecastResultHeadline({}), 'Результатов прогноза пока нет')
})

test('forecastResultHeadline when result has no numeric values', () => {
  assert.equal(
    forecastResultHeadline({ hasResult: true, forecastValues: [] }),
    'Нет оценки модели',
  )
})

test('forecastResultHeadline when values exist', () => {
  const values = [{ channelId: '1', category: 'fire-risk', value: 0.81 }]
  assert.equal(
    forecastResultHeadline({ hasResult: true, hasHighRisk: false, forecastValues: values }),
    'В норме',
  )
  assert.equal(
    forecastResultHeadline({ hasResult: true, hasHighRisk: true, forecastValues: values }),
    'Высокий риск',
  )
})

test('forecastCategoryLabel maps known codes and falls back', () => {
  assert.equal(forecastCategoryLabel('sensor-failure'), 'отказ датчика')
  assert.equal(forecastCategoryLabel('fire-risk'), 'пожарный риск')
  assert.equal(forecastCategoryLabel('unauthorized-access'), 'несанкционированный доступ')
  assert.equal(forecastCategoryLabel('infrastructure-wear'), 'износ инфраструктуры')
  assert.equal(forecastCategoryLabel('other-code'), 'other-code')
})

test('formatForecastValueList sorts by value descending', () => {
  const result = formatForecastValueList([
    { channelId: 'a', category: 'fire-risk', value: 0.2 },
    { channelId: 'b', category: 'fire-risk', value: 0.9 },
    { channelId: 'c', category: 'fire-risk', value: 0.5 },
  ])
  assert.deepEqual(
    result.map((item) => item.channelId),
    ['b', 'c', 'a'],
  )
})

test('formatForecastValueList breaks ties by channelId then category', () => {
  const result = formatForecastValueList([
    { channelId: '2', category: 'fire-risk', value: 0.5 },
    { channelId: '1', category: 'sensor-failure', value: 0.5 },
    { channelId: '1', category: 'fire-risk', value: 0.5 },
  ])
  assert.deepEqual(
    result.map((item) => `${item.channelId}:${item.category}`),
    ['1:fire-risk', '1:sensor-failure', '2:fire-risk'],
  )
})

test('formatForecastValueList always uses two decimal places', () => {
  const result = formatForecastValueList([{ channelId: '1', category: 'fire-risk', value: 0.8 }])
  assert.equal(result[0].displayValue, '0.80')
  assert.equal(result[0].value, 0.8)
})

test('formatForecastValueList returns empty for missing or empty input', () => {
  assert.deepEqual(formatForecastValueList(undefined), [])
  assert.deepEqual(formatForecastValueList(null), [])
  assert.deepEqual(formatForecastValueList([]), [])
})

test('formatForecastValueList does not mutate the source array', () => {
  const source = [
    { channelId: 'a', category: 'fire-risk', value: 0.2 },
    { channelId: 'b', category: 'fire-risk', value: 0.9 },
  ]
  formatForecastValueList(source)
  assert.equal(source[0].channelId, 'a')
  assert.equal(source[0].value, 0.2)
  assert.equal(source[1].channelId, 'b')
})
