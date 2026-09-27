import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildObjectTree } from '../prediction/buildObjectTree.js'
import { ancestorKeys, mapOwnTone, rootExpandedKeys, toMapMarkers } from './mapTreeKeys.js'

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

test('mapOwnTone is undefined without own channels', () => {
  assert.equal(mapOwnTone({ ownChannelCount: 0, ownStatuses: ['Нет связи'] }), undefined)
  assert.equal(mapOwnTone({}), undefined)
  assert.equal(mapOwnTone(undefined), undefined)
})

test('mapOwnTone is ok when own channels are normal or unnamed', () => {
  assert.equal(mapOwnTone({ ownChannelCount: 2, ownStatuses: ['Норма'] }), 'ok')
  assert.equal(mapOwnTone({ ownChannelCount: 1, ownStatuses: [] }), 'ok')
})

test('mapOwnTone is alert on any non-normal own status', () => {
  assert.equal(mapOwnTone({ ownChannelCount: 1, ownStatuses: ['Нет связи'] }), 'alert')
  assert.equal(mapOwnTone({ ownChannelCount: 2, ownStatuses: ['Норма', 'Тревога'] }), 'alert')
})

test('toMapMarkers adds tone from own channels', () => {
  const list = [
    { id: 1, longitude: 37, latitude: 55, ownChannelCount: 0, ownStatuses: [] },
    { id: 2, longitude: 37.1, latitude: 55.1, ownChannelCount: 1, ownStatuses: ['Норма'] },
    { id: 3, longitude: 37.2, latitude: 55.2, ownChannelCount: 1, ownStatuses: ['Нет связи'] },
  ]
  assert.deepEqual(toMapMarkers(list).map((m) => ({ id: m.id, tone: m.tone })), [
    { id: 1, tone: undefined },
    { id: 2, tone: 'ok' },
    { id: 3, tone: 'alert' },
  ])
})
