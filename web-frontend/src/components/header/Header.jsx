import { Button, Dropdown } from 'antd'
import { MenuOutlined, UserOutlined } from '@ant-design/icons'
import { useDispatch } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { logout } from '@/api/auth.js'
import { clearSession } from '@/store/authSlice.js'
import { toggleCollapsed } from '@/store/menuSlice.js'

import './Header.css'

const Header = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()

  const onMenuClick = async ({ key }) => {
    if (key !== 'logout') {
      return
    }

    try {
      await logout()
    } catch {
      // всё равно выходим
    }

    dispatch(clearSession())
    navigate('/login', { replace: true })
  }

  return (
    <div className="header-container">
      <div className="header-container-left">
        <Button
          type="text"
          icon={<MenuOutlined />}
          onClick={() => dispatch(toggleCollapsed())}
        />

        <span>Москоллектор</span>
      </div>

      <div className="header-container-right">
        <Dropdown
          trigger={['hover']}
          menu={{
            items: [{ key: 'logout', label: 'Выйти' }],
            onClick: onMenuClick,
          }}
        >
          <Button
            type="text"
            className="header-profile-btn"
            icon={<UserOutlined />}
          />
        </Dropdown>
      </div>
    </div>
  )
}

export default Header;
