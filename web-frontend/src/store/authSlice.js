import { createSlice } from '@reduxjs/toolkit'

function readLogin(accessToken) {
  if (!accessToken) {
    return null
  }

  try {
    const payload = accessToken.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    const claims = JSON.parse(json)
    return claims.login || claims.unique_name || null
  } catch {
    return null
  }
}

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    accessToken: null,
    login: null,
    status: 'unknown',
  },
  reducers: {
    setSession(state, action) {
      state.accessToken = action.payload
      state.login = readLogin(action.payload)
      state.status = 'authenticated'
    },
    clearSession(state) {
      state.accessToken = null
      state.login = null
      state.status = 'anonymous'
    },
  },
})

export const { setSession, clearSession } = authSlice.actions
export default authSlice.reducer
