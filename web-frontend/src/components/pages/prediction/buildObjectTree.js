export function buildObjectTree(objects) {
  const byId = new Map()
  for (const object of objects) {
    byId.set(object.id, {
      key: String(object.id),
      title: object.name,
      children: [],
    })
  }

  const roots = []
  for (const object of objects) {
    const node = byId.get(object.id)
    const parent = object.parentId == null ? null : byId.get(object.parentId)
    if (parent) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}
