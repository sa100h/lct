import assert from 'node:assert/strict'
import { test } from 'node:test'
import { REPORT_CATALOG, reportFileName } from './reportCatalog.js'

test('REPORT_CATALOG has five reports', () => {
  assert.equal(REPORT_CATALOG.length, 5)
  assert.equal(REPORT_CATALOG[0].code, 'summary')
  assert.equal(REPORT_CATALOG[0].title, 'Оперативная сводка')
  assert.equal(
    REPORT_CATALOG.some((item) => item.code === 'deviations'),
    false,
  )
})

test('reportFileName matches API stem', () => {
  assert.equal(reportFileName('svodka', '2026-09-01', '2026-09-28'), 'svodka_2026-09-01_2026-09-28.pdf')
})
