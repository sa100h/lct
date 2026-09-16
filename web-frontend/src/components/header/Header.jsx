import { Button } from 'antd'
import { MenuOutlined } from '@ant-design/icons'
import { useDispatch } from 'react-redux'
import { toggleCollapsed } from '@/store/menuSlice.js'

import './Header.css'

const Header = () => {
  const dispatch = useDispatch()

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
      
    </div>
  )
}

export default Header;