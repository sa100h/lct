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
import { useNavigate } from 'react-router-dom'
import { setSelectedKey } from '@/store/menuSlice.js'

const items = [
  { key: '/', icon: <HomeOutlined />, label: 'Главная' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Дашборд' },
  { key: '/map', icon: <FullscreenOutlined />, label: 'Карта' },
  { key: '/prediction', icon: <CloudOutlined />, label: 'Прогноз' },
  { key: '/history', icon: <HistoryOutlined />, label: 'История' },
  { key: '/notifications', icon: <NotificationOutlined />, label: 'Уведомления' },
  { key: '/reports', icon: <FileTextOutlined />, label: 'Отчеты' },
  { key: '/settings', icon: <SettingOutlined />, label: 'Настройки' },
]

export default function Sidebar() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { collapsed, selectedKey } = useSelector((state) => state.menu)

  return (
    <Menu
      mode="inline"
      inlineCollapsed={collapsed}
      selectedKeys={[selectedKey]}
      items={items}
      onClick={({ key }) => {
        dispatch(setSelectedKey(key))
        navigate(key)
      }}
    />
  )
}
