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
