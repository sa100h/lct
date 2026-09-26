import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function getDashboard() {
  const response = await apiFetch('/api/app/dashboard')
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.json()
}
