export function parseMapObjectId(search) {
  const query = search.startsWith('?') ? search.slice(1) : search
  const raw = new URLSearchParams(query).get('object')
  if (raw == null || raw === '') {
    return null
  }
  const id = Number(raw)
  return Number.isInteger(id) ? id : null
}
