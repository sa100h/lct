import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

function parseBody(text) {
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

export async function createRequest(body) {
  const response = await apiFetch('/api/app/requests', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const data = parseBody(await response.text())
  if (response.status === 201) {
    return data
  }
  throwHttpError(response.status, data)
}

export async function listRequests({ page = 1, pageSize = 20 } = {}) {
  const params = new URLSearchParams()
  params.set('page', String(page))
  params.set('pageSize', String(pageSize))
  const response = await apiFetch(`/api/app/requests?${params}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}

export async function getRequest(id) {
  const response = await apiFetch(`/api/app/requests/${id}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}

export async function updateRequestStatus(id, status) {
  const response = await apiFetch(`/api/app/requests/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
  const data = parseBody(await response.text())
  if (response.status === 204) {
    return
  }
  throwHttpError(response.status, data)
}
