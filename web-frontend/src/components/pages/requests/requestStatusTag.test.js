import assert from 'node:assert/strict'
import { test } from 'node:test'
import { requestStatusTagColor } from './requestStatusTag.js'

test('requestStatusTagColor maps known statuses', () => {
  assert.equal(requestStatusTagColor('Новая'), 'blue')
  assert.equal(requestStatusTagColor('В работе'), 'orange')
  assert.equal(requestStatusTagColor('Закрыта'), 'green')
})

test('requestStatusTagColor falls back to default', () => {
  assert.equal(requestStatusTagColor(''), 'default')
  assert.equal(requestStatusTagColor('Другой'), 'default')
  assert.equal(requestStatusTagColor(undefined), 'default')
})
