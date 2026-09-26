import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseMapObjectId } from './mapObjectQuery.js'

test('parses integer object id', () => {
  assert.equal(parseMapObjectId('?object=5'), 5)
  assert.equal(parseMapObjectId('object=5'), 5)
})

test('returns null when missing or invalid', () => {
  assert.equal(parseMapObjectId(''), null)
  assert.equal(parseMapObjectId('?object='), null)
  assert.equal(parseMapObjectId('?object=abc'), null)
  assert.equal(parseMapObjectId('?foo=1'), null)
})
