import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  MODULES,
  getAllowedModules,
  getFirstAllowedPath,
  isPathAllowed,
} from './modules.js'

const ORDER = [
  '/',
  '/dashboard',
  '/map',
  '/prediction',
  '/history',
  '/notifications',
  '/reports',
  '/settings',
]

test('MODULES order is canonical', () => {
  assert.deepEqual(MODULES.map((m) => m.path), ORDER)
})

test('getAllowedModules keeps canonical order', () => {
  const allowed = getAllowedModules(['module.settings', 'module.home', 'module.map'])
  assert.deepEqual(allowed.map((m) => m.path), ['/', '/map', '/settings'])
})

test('getFirstAllowedPath is first in MODULES not in caller order', () => {
  assert.equal(getFirstAllowedPath(['module.settings', 'module.map']), '/map')
})

test('empty permissions hide all modules and have no fallback path', () => {
  assert.deepEqual(getAllowedModules([]), [])
  assert.equal(getFirstAllowedPath([]), null)
  assert.equal(isPathAllowed([], '/'), false)
})

test('isPathAllowed matches permission for path', () => {
  const technician = ['module.home', 'module.map', 'module.prediction', 'module.history']
  assert.equal(isPathAllowed(technician, '/'), true)
  assert.equal(isPathAllowed(technician, '/settings'), false)
})
