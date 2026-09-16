import { ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { Provider } from 'react-redux'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import i18n from '@/i18n/index.js'
import Home from '@/components/homePage/Home.jsx'
import { store } from '@/store/index.js'

const router = createBrowserRouter([{ path: '/', element: <Home /> }])

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
