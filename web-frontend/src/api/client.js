import { refresh, AuthHttpError } from '@/api/auth.js'
import { clearSession, setSession } from '@/store/authSlice.js'
import { store } from '@/store/index.js'

export async function apiFetch(path, options = {}) {
  return send(path, options, false)
}

async function send(path, options, isRetry) {
  const headers = new Headers(options.headers)
  const accessToken = store.getState().auth.accessToken

  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (response.status !== 401 || isRetry) {
    return response
  }

  try {
    const nextToken = await refresh()
    store.dispatch(setSession(nextToken))
    return send(path, options, true)
  } catch {
    store.dispatch(clearSession())
    throw new AuthHttpError(401)
  }
}
