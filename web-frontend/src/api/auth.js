export class AuthHttpError extends Error {
  constructor(status) {
    super(`HTTP ${status}`)
    this.name = 'AuthHttpError'
    this.status = status
  }
}

let refreshPromise = null

async function readAccessToken(response) {
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }

  const data = await response.json()
  return data.accessToken
}

export async function login(login, password) {
  let response

  try {
    response = await fetch('/api/app/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login, password }),
    })
  } catch {
    throw new AuthHttpError(0)
  }

  return readAccessToken(response)
}

async function refreshOnce() {
  let response

  try {
    response = await fetch('/api/app/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    throw new AuthHttpError(0)
  }

  return readAccessToken(response)
}

export function refresh() {
  if (!refreshPromise) {
    refreshPromise = refreshOnce().finally(() => {
      refreshPromise = null
    })
  }

  return refreshPromise
}

export async function logout() {
  try {
    await fetch('/api/app/auth/logout', {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    // вызывающий всё равно делает clearSession
  }
}
