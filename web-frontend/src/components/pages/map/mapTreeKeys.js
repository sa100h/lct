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

export function mergeExpandedKeys(current, objects, id) {
  return [...new Set([...(current ?? []), ...ancestorKeys(objects, id)])]
}

export function scrollTreeToKey(tree, key) {
  if (tree == null || key == null) {
    return
  }
  const id = String(key)
  const run = () => {
    tree.scrollTo?.({ key: id })
    const node =
      tree.nativeElement?.querySelector?.('.ant-tree-treenode-selected') ??
      document.querySelector('.map-tree .ant-tree-treenode-selected')
    node?.scrollIntoView?.({ block: 'nearest' })
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(run)
  })
}

export function toMapMarkers(objects, toneOf) {
  return objects.map((object) => {
    const marker = {
      id: object.id,
      coordinates: [object.longitude, object.latitude],
    }
    const tone = toneOf ? toneOf(object) : mapOwnTone(object)
    if (tone) {
      marker.tone = tone
    }
    return marker
  })
}

export function mapForecastTone(hasHighRisk) {
  if (hasHighRisk === true) {
    return 'alert'
  }
  if (hasHighRisk === false) {
    return 'ok'
  }
  return 'none'
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
