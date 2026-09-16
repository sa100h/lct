import { ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { Provider } from 'react-redux'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import i18n from '@/i18n/index.js'

import AppLayout from '@/components/appLayout/AppLayout.jsx'
import Home from '../pages/homePage/Home'
import Dashboard from '../pages/dashboard/Dashboard'
import Map from '../pages/map/Map'
import Prediction from '../pages/prediction/Prediction'
import History from '../pages/history/History'
import Notifications from '../pages/notifications/Notifications'
import Reports from '../pages/reports/Reports'
import Settings from '../pages/settings/Settings'

import { store } from '@/store/index.js'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [{ index: true, element: <Home /> }],
  },
  {
    path: '/dashboard',
    element: <AppLayout />,
    children: [{ index: true, element: <Dashboard /> }],
  },
  {
    path: '/map',
    element: <AppLayout />,
    children: [{ index: true, element: <Map /> }],
  },
  {
    path: '/prediction',
    element: <AppLayout />,
    children: [{ index: true, element: <Prediction /> }],
  },
  {
    path: '/history',
    element: <AppLayout />,
    children: [{ index: true, element: <History /> }],
  },
  {
    path: '/notifications',
    element: <AppLayout />,
    children: [{ index: true, element: <Notifications /> }],
  },
  {
    path: '/reports',
    element: <AppLayout />,
    children: [{ index: true, element: <Reports /> }],
  },
  {
    path: '/settings',
    element: <AppLayout />,
    children: [{ index: true, element: <Settings /> }],
  },

])

export default function App() {
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
