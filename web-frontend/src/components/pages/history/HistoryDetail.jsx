import { useCallback, useEffect, useState } from 'react'
import { Alert, Breadcrumb, Button, Modal, Spin, Tree } from 'antd'
import { Link, useParams } from 'react-router-dom'
import { AuthHttpError } from '@/api/auth.js'
import { getForecastHistory } from '@/api/forecastHistory.js'
import { buildObjectTree } from '@/components/pages/prediction/buildObjectTree.js'
import { ancestorKeys, rootExpandedKeys } from '@/components/pages/map/mapTreeKeys.js'
import { formatObjectCount } from '@/components/objectTree/formatObjectCount.js'
import YandexMap from '@/components/pages/map/YandexMap.jsx'
import '@/components/pages/map/Map.css'
import './HistoryDetail.css'

const MISSING_KEY_TEXT =
  'Не задан ключ Яндекс.Карт (VITE_YANDEX_MAPS_API_KEY). Добавьте его в корневой .env и перезапустите Vite или пересоберите образ.'

const LOAD_ERROR_TEXT =
  'Не удалось загрузить Яндекс.Карты. Проверьте ключ, сеть и ограничения ключа по HTTP Referrer.'

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

function toHistoryMarkers(objects) {
  return objects.map((object) => ({
    id: object.id,
    coordinates: [object.longitude, object.latitude],
    tone: object.hasHighRisk ? 'risk' : 'ok',
  }))
}

export default function HistoryDetail() {
  const { id } = useParams()
  const apikey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
  const [detail, setDetail] = useState(null)
  const [treeData, setTreeData] = useState([])
  const [markers, setMarkers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [expandedKeys, setExpandedKeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [modalObject, setModalObject] = useState(null)

  const handleError = useCallback(() => {
    setLoadError(true)
  }, [])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      setNotFound(false)
      try {
        const snapshot = await getForecastHistory(id)
        if (cancelled) {
          return
        }
        const list = snapshot.objects ?? []
        const tree = buildObjectTree(list)
        setDetail(snapshot)
        setTreeData(tree)
        setMarkers(toHistoryMarkers(list))
        setExpandedKeys(rootExpandedKeys(tree))
        setSelectedId(tree[0] ? Number(tree[0].key) : null)
      } catch (caught) {
        if (cancelled) {
          return
        }
        setDetail(null)
        setTreeData([])
        setMarkers([])
        setSelectedId(null)
        if (caught instanceof AuthHttpError && caught.status === 404) {
          setNotFound(true)
          setError('Прогноз не найден')
        } else {
          setError(
            caught instanceof AuthHttpError && caught.status === 403
              ? 'Нет доступа к истории'
              : 'Не удалось загрузить прогноз',
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [id])

  const selectFromMap = (objectId) => {
    const list = detail?.objects ?? []
    setSelectedId(objectId)
    setExpandedKeys((current) => {
      const extra = ancestorKeys(list, objectId)
      return [...new Set([...current, ...extra])]
    })
  }

  const openModal = (key) => {
    const object = detail?.objects?.find((item) => String(item.id) === String(key))
    if (object) {
      setModalObject(object)
    }
  }

  if (loading) {
    return <Spin className="history-detail-spin" />
  }

  if (error) {
    return (
      <div className="history-detail-error">
        <Breadcrumb
          items={[
            { title: <Link to="/prediction">Прогноз</Link> },
            { title: 'Прогноз' },
          ]}
        />
        <Alert type="error" showIcon message={error} />
        {notFound ? <Link to="/prediction">К списку истории</Link> : null}
      </div>
    )
  }

  const showAlert = !apikey || loadError
  const alertText = !apikey ? MISSING_KEY_TEXT : LOAD_ERROR_TEXT
  const objects = detail?.objects ?? []

  return (
    <div className="history-detail">
      <Breadcrumb
        items={[
          { title: <Link to="/prediction">Прогноз</Link> },
          { title: `Прогноз ${formatWhen(detail.createdAt)}` },
        ]}
      />
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
            <span className="map-page-list-count">{formatObjectCount(objects.length)}</span>
          </div>
          <div className="map-page-list-body">
            <Tree
              className="map-tree"
              blockNode
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
              titleRender={(node) => (
                <span
                  onDoubleClick={(event) => {
                    event.stopPropagation()
                    openModal(node.key)
                  }}
                >
                  {node.title}
                </span>
              )}
            />
          </div>
        </div>
      </div>
      <Modal
        open={modalObject != null}
        title={modalObject?.name}
        footer={null}
        onCancel={() => setModalObject(null)}
      >
        {modalObject ? (
          <div className="history-detail-modal">
            <p>
              Координаты: {modalObject.latitude}; {modalObject.longitude}
            </p>
            <p>
              Статусы:{' '}
              {modalObject.statuses?.length > 0
                ? modalObject.statuses.join(', ')
                : 'нет'}
            </p>
            <p>Результатов прогноза пока нет</p>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
