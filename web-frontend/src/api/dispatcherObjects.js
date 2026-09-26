import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function listDispatcherObjects() {
  const response = await apiFetch('/api/app/dispatcher_objects')
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}
