export function rootExpandedKeys(tree) {
  return tree.map((node) => node.key)
}

export function ancestorKeys(objects, id) {
  const byId = new Map(objects.map((object) => [object.id, object]))
  const keys = []
  let current = byId.get(id)
  while (current?.parentId != null) {
    const parent = byId.get(current.parentId)
    if (!parent) {
      break
    }
    keys.push(String(parent.id))
    current = parent
  }
  return keys
}

export function toMapMarkers(objects) {
  return objects.map((object) => {
    const marker = {
      id: object.id,
      coordinates: [object.longitude, object.latitude],
    }
    const tone = mapOwnTone(object)
    if (tone) {
      marker.tone = tone
    }
    return marker
  })
}

const NORMAL = 'Норма'

export function mapOwnTone(object) {
  const count = object?.ownChannelCount ?? 0
  if (count === 0) {
    return undefined
  }
  const statuses = object.ownStatuses ?? []
  if (statuses.length === 0 || statuses.every((status) => status === NORMAL)) {
    return 'ok'
  }
  return 'alert'
}
