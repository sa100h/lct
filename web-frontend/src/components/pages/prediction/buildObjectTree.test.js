import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildObjectTree } from './buildObjectTree.js'

test('builds nested tree from parentId', () => {
  const tree = buildObjectTree([
    { id: 5773, parentId: null, name: 'Район' },
    { id: 5, parentId: 5773, name: 'объект Альфа' },
    { id: 5122, parentId: 5, name: 'ДУ объект Альфа' },
  ])
  assert.equal(tree.length, 1)
  assert.deepEqual(tree[0], {
    key: '5773',
    title: 'Район',
    children: [
      {
        key: '5',
        title: 'объект Альфа',
        children: [
          { key: '5122', title: 'ДУ объект Альфа', children: [] },
        ],
      },
    ],
  })
})

test('unknown parentId becomes a root', () => {
  const tree = buildObjectTree([
    { id: 20, parentId: 6, name: 'объект Фита' },
  ])
  assert.deepEqual(tree, [{ key: '20', title: 'объект Фита', children: [] }])
})

test('keeps multiple roots', () => {
  const tree = buildObjectTree([
    { id: 1, parentId: null, name: 'A' },
    { id: 2, parentId: null, name: 'B' },
  ])
  assert.equal(tree.length, 2)
  assert.equal(tree[0].key, '1')
  assert.equal(tree[1].key, '2')
})
