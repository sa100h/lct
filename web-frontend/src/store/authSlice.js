import { createSlice } from '@reduxjs/toolkit'

function readClaims(accessToken) {
  if (!accessToken) {
    return null
  }

  try {
    const payload = accessToken.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return null
  }
}

function readLogin(accessToken) {
  const claims = readClaims(accessToken)
  return claims?.login || claims?.unique_name || null
}

function readPermissions(accessToken) {
  const raw = readClaims(accessToken)?.permissions
  return Array.isArray(raw) ? raw.filter((value) => typeof value === 'string') : []
}

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    accessToken: null,
    login: null,
    permissions: [],
    status: 'unknown',
  },
  reducers: {
    setSession(state, action) {
      state.accessToken = action.payload
      state.login = readLogin(action.payload)
      state.permissions = readPermissions(action.payload)
      state.status = 'authenticated'
    },
    clearSession(state) {
      state.accessToken = null
      state.login = null
      state.permissions = []
      state.status = 'anonymous'
    },
  },
})

export const { setSession, clearSession } = authSlice.actions
export default authSlice.reducer
