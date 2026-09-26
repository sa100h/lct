import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildObjectTree } from '../prediction/buildObjectTree.js'
import { ancestorKeys, rootExpandedKeys, toMapMarkers } from './mapTreeKeys.js'

const objects = [
  { id: 5773, parentId: null, name: 'Район', longitude: 37.6, latitude: 55.7 },
  { id: 5, parentId: 5773, name: 'объект Альфа', longitude: 37.5, latitude: 55.61 },
  { id: 5122, parentId: 5, name: 'ДУ', longitude: 37.51, latitude: 55.62 },
]

test('rootExpandedKeys are root keys only', () => {
  const tree = buildObjectTree(objects)
  assert.deepEqual(rootExpandedKeys(tree), ['5773'])
})

test('ancestorKeys walks parentId without self', () => {
  assert.deepEqual(ancestorKeys(objects, 5122).sort(), ['5', '5773'].sort())
  assert.deepEqual(ancestorKeys(objects, 5773), [])
  assert.deepEqual(ancestorKeys(objects, 999), [])
})

test('toMapMarkers uses longitude then latitude', () => {
  assert.deepEqual(toMapMarkers(objects)[1], { id: 5, coordinates: [37.5, 55.61] })
})
