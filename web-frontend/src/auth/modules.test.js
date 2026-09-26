import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  MODULES,
  getAllowedModules,
  getFirstAllowedPath,
  getSelectedMenuKey,
  isPathAllowed,
} from './modules.js'

const ORDER = [
  '/',
  '/map',
  '/prediction',
  '/notifications',
  '/reports',
  '/settings',
]

test('MODULES order is canonical and has no history item', () => {
  assert.deepEqual(MODULES.map((m) => m.path), ORDER)
  assert.equal(
    MODULES.some((m) => m.path === '/history'),
    false,
  )
})

test('dashboard lives at / with module.dashboard', () => {
  assert.equal(MODULES[0].permission, 'module.dashboard')
  assert.equal(MODULES[0].label, 'Дашборд')
  assert.equal(
    MODULES.some((m) => m.path === '/dashboard' || m.permission === 'module.home'),
    false,
  )
})

test('prediction menu item uses either forecast permission', () => {
  const prediction = MODULES.find((m) => m.path === '/prediction')
  assert.deepEqual(prediction.anyPermissions, [
    'module.prediction',
    'module.history',
  ])
  assert.equal(prediction.label, 'Прогноз')
})

test('getAllowedModules keeps canonical order', () => {
  const allowed = getAllowedModules(['module.settings', 'module.dashboard', 'module.map'])
  assert.deepEqual(allowed.map((m) => m.path), ['/', '/map', '/settings'])
})

test('getAllowedModules shows Прогноз for either permission', () => {
  assert.deepEqual(
    getAllowedModules(['module.prediction']).map((m) => m.path),
    ['/prediction'],
  )
  assert.deepEqual(
    getAllowedModules(['module.history']).map((m) => m.path),
    ['/prediction'],
  )
  assert.deepEqual(
    getAllowedModules(['module.prediction', 'module.history']).map((m) => m.path),
    ['/prediction'],
  )
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

test('isPathAllowed opens /prediction for either forecast permission', () => {
  assert.equal(isPathAllowed(['module.prediction'], '/prediction'), true)
  assert.equal(isPathAllowed(['module.history'], '/prediction'), true)
  assert.equal(isPathAllowed(['module.map'], '/prediction'), false)
})

test('isPathAllowed opens exact /history for either forecast permission', () => {
  assert.equal(isPathAllowed(['module.prediction'], '/history'), true)
  assert.equal(isPathAllowed(['module.history'], '/history'), true)
  assert.equal(isPathAllowed(['module.map'], '/history'), false)
})

test('isPathAllowed treats /history/:id as module.history only', () => {
  const id = '/history/2c059017-47c7-480a-b0a1-516be249695d'
  assert.equal(isPathAllowed(['module.history'], id), true)
  assert.equal(isPathAllowed(['module.prediction'], id), false)
  assert.equal(isPathAllowed(['module.map'], '/history/abc'), false)
})

test('getSelectedMenuKey highlights Прогноз on history routes', () => {
  assert.equal(getSelectedMenuKey('/prediction'), '/prediction')
  assert.equal(getSelectedMenuKey('/history'), '/prediction')
  assert.equal(
    getSelectedMenuKey('/history/2c059017-47c7-480a-b0a1-516be249695d'),
    '/prediction',
  )
  assert.equal(getSelectedMenuKey('/map'), '/map')
  assert.equal(getSelectedMenuKey('/'), '/')
})
