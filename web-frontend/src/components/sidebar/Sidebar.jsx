import { 
  HomeOutlined,
  DashboardOutlined,
  FullscreenOutlined,
  CloudOutlined,
  HistoryOutlined,
  NotificationOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Menu } from 'antd'
import { useDispatch, useSelector } from 'react-redux'
import { useLocation, useNavigate } from 'react-router-dom'
import { getAllowedModules } from '@/auth/modules.js'
import { setSelectedKey } from '@/store/menuSlice.js'

const ICONS = {
  '/': <HomeOutlined />,
  '/dashboard': <DashboardOutlined />,
  '/map': <FullscreenOutlined />,
  '/prediction': <CloudOutlined />,
  '/history': <HistoryOutlined />,
  '/notifications': <NotificationOutlined />,
  '/reports': <FileTextOutlined />,
  '/settings': <SettingOutlined />,
}

export default function Sidebar() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const location = useLocation()
  const { collapsed } = useSelector((state) => state.menu)
  const permissions = useSelector((state) => state.auth.permissions)
  const items = getAllowedModules(permissions).map((module) => ({
    key: module.path,
    icon: ICONS[module.path],
    label: module.label,
  }))

  return (
    <Menu
      mode="inline"
      inlineCollapsed={collapsed}
      selectedKeys={[location.pathname]}
      items={items}
      onClick={({ key }) => {
        dispatch(setSelectedKey(key))
        navigate(key)
      }}
    />
  )
}
