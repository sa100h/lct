import assert from 'node:assert/strict'
import { test } from 'node:test'
import reducer, { clearSession, setSession } from './authSlice.js'

function tokenWith(payload) {
  const body = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64')
  return `eyJhbGciOiJub25lIn0.${body}.x`
}

test('setSession reads permissions array from jwt', () => {
  const token = tokenWith({
    login: 'admin.test',
    permissions: ['demo.access', 'module.dashboard'],
  })
  const state = reducer(
    { accessToken: null, login: null, permissions: [], status: 'unknown' },
    setSession(token),
  )
  assert.deepEqual(state.permissions, ['demo.access', 'module.dashboard'])
  assert.equal(state.login, 'admin.test')
  assert.equal(state.status, 'authenticated')
})

test('setSession uses empty permissions when claim is not an array', () => {
  const token = tokenWith({ login: 'x', permissions: 'demo.access' })
  const state = reducer(
    { accessToken: null, login: null, permissions: ['stale'], status: 'unknown' },
    setSession(token),
  )
  assert.deepEqual(state.permissions, [])
})

test('clearSession resets permissions', () => {
  const state = reducer(
    {
      accessToken: 't',
      login: 'x',
      permissions: ['module.dashboard'],
      status: 'authenticated',
    },
    clearSession(),
  )
  assert.deepEqual(state.permissions, [])
  assert.equal(state.login, null)
  assert.equal(state.status, 'anonymous')
})
