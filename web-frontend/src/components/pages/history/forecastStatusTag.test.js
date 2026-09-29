import assert from 'node:assert/strict'
import { test } from 'node:test'
import { FORECAST_STATUS_LABEL, forecastStatusTagColor } from './forecastStatusTag.js'

test('forecastStatusTagColor maps known statuses', () => {
  assert.equal(forecastStatusTagColor('pending'), 'blue')
  assert.equal(forecastStatusTagColor('running'), 'orange')
  assert.equal(forecastStatusTagColor('done'), 'green')
  assert.equal(forecastStatusTagColor('approved'), 'cyan')
})

test('forecastStatusTagColor falls back to default', () => {
  assert.equal(forecastStatusTagColor(''), 'default')
  assert.equal(forecastStatusTagColor('other'), 'default')
  assert.equal(forecastStatusTagColor(undefined), 'default')
})

test('FORECAST_STATUS_LABEL is Russian', () => {
  assert.equal(FORECAST_STATUS_LABEL.pending, 'Ожидание')
  assert.equal(FORECAST_STATUS_LABEL.running, 'В работе')
  assert.equal(FORECAST_STATUS_LABEL.done, 'Готово')
  assert.equal(FORECAST_STATUS_LABEL.approved, 'Обработан')
})
