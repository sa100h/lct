import { useSelector } from 'react-redux'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'

export default function GuestOnly({ children }) {
  const status = useSelector((state) => state.auth.status)

  if (status === 'unknown') {
    return <Spin style={{ display: 'block', margin: '48px auto' }} />
  }

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  return children
}
