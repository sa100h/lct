import { Button, Dropdown } from 'antd'
import { DownOutlined, MenuOutlined, UserOutlined } from '@ant-design/icons'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { logout } from '@/api/auth.js'
import { clearSession } from '@/store/authSlice.js'
import { toggleCollapsed } from '@/store/menuSlice.js'

import './Header.css'

const Header = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const login = useSelector((state) => state.auth.login)

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
          <div className="header-profile">
            <UserOutlined className="header-profile-icon" />
            {login ? <span className="header-profile-name">{login}</span> : null}
            <DownOutlined className="header-profile-chevron" />
          </div>
        </Dropdown>
      </div>
    </div>
  )
}

export default Header;
