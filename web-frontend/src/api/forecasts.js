import { AuthHttpError } from '@/api/auth.js'
import { apiFetch } from '@/api/client.js'
import { forecastErrorMessage } from '@/api/forecastMessages.js'

export { formatForecastStartedMessage, forecastErrorMessage } from '@/api/forecastMessages.js'

export async function runForecast(dispatcherObjectIds) {
  const response = await apiFetch('/api/app/forecasts/run', {
    method: 'POST',
    body: JSON.stringify({ dispatcherObjectIds }),
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
  if (response.status === 202) {
    return data
  }
  const error = new AuthHttpError(response.status)
  error.displayMessage = forecastErrorMessage(response.status, data)
  throw error
}
