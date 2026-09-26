export const MODULES = [
  { path: '/', permission: 'module.dashboard', label: 'Дашборд' },
  { path: '/map', permission: 'module.map', label: 'Карта' },
  { path: '/prediction', permission: 'module.prediction', label: 'Прогноз' },
  { path: '/history', permission: 'module.history', label: 'История' },
  { path: '/notifications', permission: 'module.notifications', label: 'Уведомления' },
  { path: '/reports', permission: 'module.reports', label: 'Отчеты' },
  { path: '/settings', permission: 'module.settings', label: 'Настройки' },
]

export function getAllowedModules(permissions) {
  const set = new Set(permissions)
  return MODULES.filter((module) => set.has(module.permission))
}

export function getFirstAllowedPath(permissions) {
  return getAllowedModules(permissions)[0]?.path ?? null
}

export function isPathAllowed(permissions, path) {
  return getAllowedModules(permissions).some((module) => module.path === path)
}
