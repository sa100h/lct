import assert from 'node:assert/strict'
import { test } from 'node:test'
import { forecastCategoryLabel, forecastResultHeadline } from './forecastResultCopy.js'

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
