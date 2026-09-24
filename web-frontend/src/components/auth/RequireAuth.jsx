import { useSelector } from 'react-redux'
import { Navigate } from 'react-router-dom'

export default function RequireAuth({ children }) {
  const status = useSelector((state) => state.auth.status)

  if (status === 'unknown') {
    return null
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" replace />
  }

  return children
}
