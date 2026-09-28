import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function createRequest(body) {
  const response = await apiFetch('/api/app/requests', {
    method: 'POST',
    body: JSON.stringify(body),
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
  if (response.status === 201) {
    return data
  }
  const error = new AuthHttpError(response.status)
  if (data && typeof data.error === 'string' && data.error) {
    error.displayMessage = data.error
  }
  throw error
}
