import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isValidReportRange } from './reportPeriod.js'

test('isValidReportRange rejects inverted and empty', () => {
  assert.equal(isValidReportRange('2026-09-02', '2026-09-01'), false)
  assert.equal(isValidReportRange('', '2026-09-01'), false)
  assert.equal(isValidReportRange('2026-09-01', '2026-09-01'), true)
})
