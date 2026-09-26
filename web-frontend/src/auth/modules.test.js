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

test('dashboard lives at / with module.dashboard', () => {
  assert.equal(MODULES[0].permission, 'module.dashboard')
  assert.equal(MODULES[0].label, 'Дашборд')
  assert.equal(
    MODULES.some((m) => m.path === '/dashboard' || m.permission === 'module.home'),
    false,
  )
})

test('getAllowedModules keeps canonical order', () => {
  const allowed = getAllowedModules(['module.settings', 'module.dashboard', 'module.map'])
  assert.deepEqual(allowed.map((m) => m.path), ['/', '/map', '/settings'])
})

test('getFirstAllowedPath is first in MODULES not in caller order', () => {
  assert.equal(getFirstAllowedPath(['module.settings', 'module.map']), '/map')
  assert.equal(getFirstAllowedPath(['module.map', 'module.dashboard']), '/')
})

test('empty permissions hide all modules and have no fallback path', () => {
  assert.deepEqual(getAllowedModules([]), [])
  assert.equal(getFirstAllowedPath([]), null)
  assert.equal(isPathAllowed([], '/'), false)
})

test('isPathAllowed matches permission for path', () => {
  const technician = ['module.map', 'module.prediction', 'module.history']
  assert.equal(isPathAllowed(technician, '/'), false)
  assert.equal(isPathAllowed(technician, '/map'), true)
  assert.equal(isPathAllowed(technician, '/settings'), false)
  assert.equal(isPathAllowed(['module.dashboard'], '/'), true)
  assert.equal(isPathAllowed(['module.dashboard'], '/dashboard'), false)
})

test('isPathAllowed treats /history/:id as module.history', () => {
  const history = ['module.history']
  assert.equal(isPathAllowed(history, '/history'), true)
  assert.equal(
    isPathAllowed(history, '/history/2c059017-47c7-480a-b0a1-516be249695d'),
    true,
  )
  assert.equal(isPathAllowed(history, '/map'), false)
  assert.equal(isPathAllowed(['module.map'], '/history/abc'), false)
})
