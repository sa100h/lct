import { ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import i18n from '@/i18n/index.js'
import Home from '@/components/Home.jsx'

const router = createBrowserRouter([{ path: '/', element: <Home /> }])

export default function App() {
  return (
    <ConfigProvider>
      <I18nextProvider i18n={i18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </ConfigProvider>
  )
}
