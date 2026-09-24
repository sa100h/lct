import { createSlice } from '@reduxjs/toolkit'

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    accessToken: null,
    status: 'unknown',
  },
  reducers: {
    setSession(state, action) {
      state.accessToken = action.payload
      state.status = 'authenticated'
    },
    clearSession(state) {
      state.accessToken = null
      state.status = 'anonymous'
    },
  },
})

export const { setSession, clearSession } = authSlice.actions
export default authSlice.reducer
