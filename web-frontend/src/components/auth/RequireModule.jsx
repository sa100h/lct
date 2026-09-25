import { useSelector } from 'react-redux'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getFirstAllowedPath, isPathAllowed } from '@/auth/modules.js'

export default function RequireModule() {
  const location = useLocation()
  const permissions = useSelector((state) => state.auth.permissions)
  if (isPathAllowed(permissions, location.pathname)) {
    return <Outlet />
  }

  const fallback = getFirstAllowedPath(permissions)
  if (fallback == null) {
    return <Outlet />
  }

  return <Navigate to={fallback} replace />
}
