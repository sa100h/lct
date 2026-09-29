import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

function parseJson(text) {
  if (!text) {
    return null
  }
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function throwHttpError(status, data) {
  const error = new AuthHttpError(status)
  if (data && typeof data.error === 'string' && data.error) {
    error.displayMessage = data.error
  }
  throw error
}

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

async function postForecastAction(path) {
  const response = await apiFetch(path, { method: 'POST' })
  const data = parseJson(await response.text())
  if (response.status === 204) {
    return
  }
  throwHttpError(response.status, data)
}

export async function approveForecast(id) {
  await postForecastAction(`/api/app/forecasts/${id}/approve`)
}

export async function markForecastErroneous(id, dispatcherObjectIds) {
  const response = await apiFetch(`/api/app/forecasts/${id}/erroneous`, {
    method: 'POST',
    body: JSON.stringify({ dispatcherObjectIds }),
  })
  const data = parseJson(await response.text())
  if (response.status === 204) {
    return
  }
  throwHttpError(response.status, data)
}
