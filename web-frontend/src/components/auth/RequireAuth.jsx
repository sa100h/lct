import { useSelector } from 'react-redux'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'

export default function RequireAuth({ children }) {
  const status = useSelector((state) => state.auth.status)

  if (status === 'unknown') {
    return <Spin style={{ display: 'block', margin: '48px auto' }} />
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" replace />
  }

  return children
}
