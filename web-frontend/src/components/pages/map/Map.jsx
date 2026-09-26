import { useCallback, useState, useEffect } from 'react'
import { Alert, Button, Spin, Tree } from 'antd'
import { AuthHttpError } from '@/api/auth.js'
import { listDispatcherObjects } from '@/api/dispatcherObjects.js'
import { buildObjectTree } from '@/components/pages/prediction/buildObjectTree.js'
import { ancestorKeys, rootExpandedKeys, toMapMarkers } from './mapTreeKeys.js'
import { formatObjectCount } from '@/components/objectTree/formatObjectCount.js'
import YandexMap from './YandexMap.jsx'
import './Map.css'

const MISSING_KEY_TEXT =
  'Не задан ключ Яндекс.Карт (VITE_YANDEX_MAPS_API_KEY). Добавьте его в корневой .env и перезапустите Vite или пересоберите образ.'

const LOAD_ERROR_TEXT =
  'Не удалось загрузить Яндекс.Карты. Проверьте ключ, сеть и ограничения ключа по HTTP Referrer.'

export default function MapPage() {
  const apikey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
  const [objects, setObjects] = useState([])
  const [treeData, setTreeData] = useState([])
  const [markers, setMarkers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [expandedKeys, setExpandedKeys] = useState([])
  const [objectsLoading, setObjectsLoading] = useState(true)
  const [objectsError, setObjectsError] = useState(null)
  const [loadError, setLoadError] = useState(false)

  const handleError = useCallback(() => {
    setLoadError(true)
  }, [])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setObjectsLoading(true)
      setObjectsError(null)
      try {
        const list = await listDispatcherObjects()
        if (cancelled) {
          return
        }
        const tree = buildObjectTree(list)
        setObjects(list)
        setTreeData(tree)
        setMarkers(toMapMarkers(list))
        setExpandedKeys(rootExpandedKeys(tree))
        setSelectedId(tree[0] ? Number(tree[0].key) : null)
      } catch (error) {
        if (cancelled) {
          return
        }
        setObjects([])
        setTreeData([])
        setMarkers([])
        setSelectedId(null)
        setExpandedKeys([])
        setObjectsError(
          error instanceof AuthHttpError && error.status === 403
            ? 'Нет доступа к списку объектов'
            : 'Не удалось загрузить список объектов',
        )
      } finally {
        if (!cancelled) {
          setObjectsLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const selectFromMap = (id) => {
    setSelectedId(id)
    setExpandedKeys((current) => {
      const extra = ancestorKeys(objects, id)
      return [...new Set([...current, ...extra])]
    })
  }

  const showAlert = !apikey || loadError
  const alertText = !apikey ? MISSING_KEY_TEXT : LOAD_ERROR_TEXT

  return (
    <div className="map-page">
      <div className="map-page-main">
        {showAlert ? (
          <div className="map-page-error">
            <Alert type="error" showIcon message={alertText} />
            <Button onClick={() => window.location.reload()}>Обновить</Button>
          </div>
        ) : (
          <YandexMap
            apikey={apikey}
            markers={markers}
            selectedId={selectedId}
            onSelect={selectFromMap}
            onError={handleError}
          />
        )}
      </div>
      <div className="map-page-list">
        <div className="map-page-list-header">
          <h2>Объекты</h2>
          <span className="map-page-list-count">
            {objectsLoading ? 'Загрузка…' : formatObjectCount(objects.length)}
          </span>
        </div>
        <div className="map-page-list-body">
          {objectsError ? (
            <Alert type="error" showIcon message={objectsError} />
          ) : null}
          {objectsLoading ? (
            <Spin />
          ) : (
            <Tree
              className="map-tree"
              blockNode
              showLine={{ showLeafIcon: false }}
              treeData={treeData}
              selectedKeys={selectedId == null ? [] : [String(selectedId)]}
              expandedKeys={expandedKeys}
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={(keys) => {
                if (keys.length === 0) {
                  return
                }
                setSelectedId(Number(keys[0]))
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
