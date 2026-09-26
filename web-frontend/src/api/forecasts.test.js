import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  forecastErrorMessage,
  formatForecastStartedMessage,
} from './forecastMessages.js'

test('formatForecastStartedMessage uses local time and fixed copy', () => {
  const text = formatForecastStartedMessage('2026-09-25T10:30:00Z')
  assert.match(text, /^Прогноз запущен в .+, ожидайте завершения$/)
})

test('forecastErrorMessage prefers API error text on 400', () => {
  assert.equal(
    forecastErrorMessage(400, { error: 'Unknown dispatcher object ids: 1' }),
    'Unknown dispatcher object ids: 1',
  )
})

test('forecastErrorMessage maps 403 and fallback', () => {
  assert.equal(forecastErrorMessage(403, null), 'Нет права запускать прогноз')
  assert.equal(forecastErrorMessage(500, null), 'Не удалось запустить прогноз')
  assert.equal(forecastErrorMessage(400, null), 'Не удалось запустить прогноз')
})
