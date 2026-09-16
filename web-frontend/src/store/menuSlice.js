import { createSlice } from '@reduxjs/toolkit'

const menuSlice = createSlice({
  name: 'menu',
  initialState: {
    collapsed: false,
    selectedKey: '/',
  },
  reducers: {
    toggleCollapsed(state) {
      state.collapsed = !state.collapsed
    },
    setSelectedKey(state, action) {
      state.selectedKey = action.payload
    },
  },
})

export const { toggleCollapsed, setSelectedKey } = menuSlice.actions
export default menuSlice.reducer
