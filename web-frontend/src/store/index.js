import { configureStore } from '@reduxjs/toolkit'
import authReducer from './authSlice.js'
import menuReducer from './menuSlice.js'

export const store = configureStore({
  reducer: {
    auth: authReducer,
    menu: menuReducer,
  },
})
