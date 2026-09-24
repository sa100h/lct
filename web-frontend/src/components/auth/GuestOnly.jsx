import { useSelector } from 'react-redux'
import { Navigate } from 'react-router-dom'

export default function GuestOnly({ children }) {
  const status = useSelector((state) => state.auth.status)

  if (status === 'unknown') {
    return null
  }

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  return children
}
