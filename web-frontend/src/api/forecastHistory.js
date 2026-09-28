import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function listForecastAuthors() {
  const response = await apiFetch('/api/app/forecasts/authors')
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}

export async function listForecastHistory({
  createdBy,
  from,
  to,
  page = 1,
  pageSize = 20,
} = {}) {
  const params = new URLSearchParams()
  if (createdBy) {
    params.set('createdBy', createdBy)
  }
  if (from) {
    params.set('from', from)
  }
  if (to) {
    params.set('to', to)
  }
  params.set('page', String(page))
  params.set('pageSize', String(pageSize))
  const response = await apiFetch(`/api/app/forecasts?${params}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}

export async function getForecastHistory(id) {
  const response = await apiFetch(`/api/app/forecasts/${id}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}

export async function markForecastErroneous(id, dispatcherObjectId) {
  const response = await apiFetch(`/api/app/forecasts/${id}/erroneous`, {
    method: 'POST',
    body: JSON.stringify({ dispatcherObjectId }),
  })
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (response.status === 204) {
    return
  }
  const error = new AuthHttpError(response.status)
  if (data && typeof data.error === 'string' && data.error) {
    error.displayMessage = data.error
  }
  throw error
}
