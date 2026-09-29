import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'

export async function getReportPdf(code, from, to) {
  const params = new URLSearchParams({ from, to })
  const response = await apiFetch(`/api/app/reports/${code}?${params}`)
  if (!response.ok) {
    throw new AuthHttpError(response.status)
  }
  return response.blob()
}
