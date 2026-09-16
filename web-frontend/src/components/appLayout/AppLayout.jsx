import { Layout } from 'antd'
import { Outlet } from 'react-router-dom'
import { useSelector } from 'react-redux'
import Header from '@/components/header/Header.jsx'
import Sidebar from '@/components/sidebar/Sidebar.jsx'
import './AppLayout.css'

const { Content, Header: LayoutHeader, Sider } = Layout

export default function AppLayout() {
  const collapsed = useSelector((state) => state.menu.collapsed)

  return (
    <Layout className="app-layout">

      <LayoutHeader className="app-layout-header">
        <Header />
      </LayoutHeader>

      <Layout>
        <Sider
          collapsed={collapsed}
          collapsible={false}
          trigger={null}
          width={200}
          collapsedWidth={80}
          theme="light"
        >
          <Sidebar />
        </Sider>

        <Content className="app-layout-content">
          <Outlet />
        </Content>
        
      </Layout>
    </Layout>
  )
}
