export const MODULES = [
  { path: '/', permission: 'module.dashboard', label: 'Дашборд' },
  { path: '/map', permission: 'module.map', label: 'Карта' },
  {
    path: '/prediction',
    anyPermissions: ['module.prediction', 'module.history'],
    label: 'Прогноз',
  },
  { path: '/notifications', permission: 'module.notifications', label: 'Уведомления' },
  { path: '/reports', permission: 'module.reports', label: 'Отчеты' },
  { path: '/settings', permission: 'module.settings', label: 'Настройки' },
]

function hasModule(set, module) {
  if (module.anyPermissions) {
    return module.anyPermissions.some((permission) => set.has(permission))
  }
  return set.has(module.permission)
}

export function getAllowedModules(permissions) {
  const set = new Set(permissions)
  return MODULES.filter((module) => hasModule(set, module))
}

export function getFirstAllowedPath(permissions) {
  return getAllowedModules(permissions)[0]?.path ?? null
}

export function isPathAllowed(permissions, path) {
  const set = new Set(permissions)
  const canForecast =
    set.has('module.prediction') || set.has('module.history')

  if (path === '/prediction' || path === '/history') {
    return canForecast
  }
  if (path.startsWith('/history/')) {
    return set.has('module.history')
  }

  return getAllowedModules(permissions).some((module) => {
    if (module.path === path) {
      return true
    }
    return module.path !== '/' && path.startsWith(`${module.path}/`)
  })
}

export function getSelectedMenuKey(pathname) {
  if (pathname === '/history' || pathname.startsWith('/history/')) {
    return '/prediction'
  }
  return pathname
}
