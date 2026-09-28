import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function listUsersByRole(role) {
  const response = await apiFetch(`/api/app/users?role=${encodeURIComponent(role)}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}
