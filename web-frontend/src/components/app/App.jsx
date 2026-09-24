import { useEffect } from 'react'
import { ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { Provider } from 'react-redux'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import i18n from '@/i18n/index.js'

import { refresh } from '@/api/auth.js'
import GuestOnly from '@/components/auth/GuestOnly.jsx'
import RequireAuth from '@/components/auth/RequireAuth.jsx'
import AppLayout from '@/components/appLayout/AppLayout.jsx'
import Login from '@/components/pages/login/Login.jsx'
import Home from '../pages/homePage/Home'
import Dashboard from '../pages/dashboard/Dashboard'
import Map from '../pages/map/Map'
import Prediction from '../pages/prediction/Prediction'
import History from '../pages/history/History'
import Notifications from '../pages/notifications/Notifications'
import Reports from '../pages/reports/Reports'
import Settings from '../pages/settings/Settings'

import { clearSession, setSession } from '@/store/authSlice.js'
import { store } from '@/store/index.js'

const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <GuestOnly>
        <Login />
      </GuestOnly>
    ),
  },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/', element: <Home /> },
      { path: '/dashboard', element: <Dashboard /> },
      { path: '/map', element: <Map /> },
      { path: '/prediction', element: <Prediction /> },
      { path: '/history', element: <History /> },
      { path: '/notifications', element: <Notifications /> },
      { path: '/reports', element: <Reports /> },
      { path: '/settings', element: <Settings /> },
    ],
  },
])

export default function App() {
  useEffect(() => {
    let cancelled = false

    const bootstrap = async () => {
      try {
        const accessToken = await refresh()
        if (!cancelled) {
          store.dispatch(setSession(accessToken))
        }
      } catch {
        if (!cancelled) {
          store.dispatch(clearSession())
        }
      }
    }

    void bootstrap()

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Provider store={store}>
      <ConfigProvider>
        <I18nextProvider i18n={i18n}>
          <RouterProvider router={router} />
        </I18nextProvider>
      </ConfigProvider>
    </Provider>
  )
}
