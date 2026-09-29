export function moscowToday() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Moscow' })
}

export function defaultReportRange() {
  const to = moscowToday()
  const [year, month, day] = to.split('-').map(Number)
  const fromDate = new Date(Date.UTC(year, month - 1, day))
  fromDate.setUTCDate(fromDate.getUTCDate() - 13)
  const from = fromDate.toISOString().slice(0, 10)
  return { from, to }
}

export function isValidReportRange(from, to) {
  return Boolean(from && to && from <= to)
}
