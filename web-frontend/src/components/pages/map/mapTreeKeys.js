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
  return objects.map((object) => ({
    id: object.id,
    coordinates: [object.longitude, object.latitude],
  }))
}
