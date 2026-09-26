import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatObjectCount } from './formatObjectCount.js'

test('russian plural for object count', () => {
  assert.equal(formatObjectCount(0), '0 объектов')
  assert.equal(formatObjectCount(1), '1 объект')
  assert.equal(formatObjectCount(2), '2 объекта')
  assert.equal(formatObjectCount(4), '4 объекта')
  assert.equal(formatObjectCount(5), '5 объектов')
  assert.equal(formatObjectCount(11), '11 объектов')
  assert.equal(formatObjectCount(21), '21 объект')
})
