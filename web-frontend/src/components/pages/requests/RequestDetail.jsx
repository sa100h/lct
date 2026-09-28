import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Breadcrumb, Button, Select, Spin, Tree, message } from 'antd'
import { Link, useParams } from 'react-router-dom'
import { AuthHttpError } from '@/api/auth.js'
import { getRequest, updateRequestStatus } from '@/api/requests.js'
import { buildObjectTree } from '@/components/pages/prediction/buildObjectTree.js'
import {
  mapOwnTone,
  mergeExpandedKeys,
  rootExpandedKeys,
  scrollTreeToKey,
  toMapMarkers,
} from '@/components/pages/map/mapTreeKeys.js'
import { formatObjectCount } from '@/components/objectTree/formatObjectCount.js'
import YandexMap from '@/components/pages/map/YandexMap.jsx'
import '@/components/pages/map/Map.css'
import './RequestDetail.css'

const MISSING_KEY_TEXT =
  'Не задан ключ Яндекс.Карт (VITE_YANDEX_MAPS_API_KEY). Добавьте его в корневой .env и перезапустите Vite или пересоберите образ.'

const LOAD_ERROR_TEXT =
  'Не удалось загрузить Яндекс.Карты. Проверьте ключ, сеть и ограничения ключа по HTTP Referrer.'

const STATUSES = ['Новая', 'В работе', 'Закрыта']

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

export default function RequestDetail() {
  const { id } = useParams()
  const apikey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
  const [detail, setDetail] = useState(null)
  const [treeData, setTreeData] = useState([])
  const [markers, setMarkers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [expandedKeys, setExpandedKeys] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const treeRef = useRef(null)

  const handleError = useCallback(() => {
    setLoadError(true)
  }, [])

  const applySnapshot = useCallback((snapshot, { keepSelection }) => {
    const list = snapshot.objects ?? []
    const tree = buildObjectTree(list)
    setDetail(snapshot)
    setStatus(snapshot.status)
    setTreeData(tree)
    setMarkers(toMapMarkers(list))
    if (keepSelection) {
      setSelectedId((current) =>
        current != null && list.some((item) => item.id === current)
          ? current
          : tree[0]
            ? Number(tree[0].key)
            : null)
    } else {
      setExpandedKeys(rootExpandedKeys(tree))
      setSelectedId(tree[0] ? Number(tree[0].key) : null)
    }
  }, [])

  const loadDetail = useCallback(async ({ showSpinner = true, keepSelection = false } = {}) => {
    if (showSpinner) {
      setLoading(true)
    }
    setError(null)
    setNotFound(false)
    try {
      const snapshot = await getRequest(id)
      applySnapshot(snapshot, { keepSelection })
    } catch (caught) {
      setDetail(null)
      setTreeData([])
      setMarkers([])
      setSelectedId(null)
      if (caught instanceof AuthHttpError && caught.status === 404) {
        setNotFound(true)
        setError('Заявка не найдена')
      } else {
        setError(
          caught instanceof AuthHttpError && caught.status === 403
            ? 'Нет доступа к заявкам'
            : 'Не удалось загрузить заявку',
        )
      }
    } finally {
      if (showSpinner) {
        setLoading(false)
      }
    }
  }, [id, applySnapshot])

  useEffect(() => {
    void loadDetail({ showSpinner: true, keepSelection: false })
  }, [loadDetail])

  const selectFromMap = (objectId) => {
    const list = detail?.objects ?? []
    setSelectedId(objectId)
    setExpandedKeys((current) => mergeExpandedKeys(current, list, objectId))
    scrollTreeToKey(treeRef.current, objectId)
  }

  const saveStatus = async () => {
    if (!status) {
      return
    }
    setSaving(true)
    try {
      await updateRequestStatus(id, status)
      message.success('Статус обновлён')
      await loadDetail({ showSpinner: false, keepSelection: true })
    } catch (caught) {
      message.error(
        caught instanceof AuthHttpError && caught.displayMessage
          ? caught.displayMessage
          : 'Не удалось сменить статус',
      )
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Spin className="request-detail-spin" />
  }

  if (error) {
    return (
      <div className="request-detail-error">
        <Breadcrumb
          items={[
            { title: <Link to="/requests">Заявки</Link> },
            { title: 'Заявка' },
          ]}
        />
        <Alert type="error" showIcon message={error} />
        {notFound ? <Link to="/requests">К списку заявок</Link> : null}
      </div>
    )
  }

  const showAlert = !apikey || loadError
  const alertText = !apikey ? MISSING_KEY_TEXT : LOAD_ERROR_TEXT
  const objects = detail?.objects ?? []

  return (
    <div className="request-detail">
      <Breadcrumb
        items={[
          { title: <Link to="/requests">Заявки</Link> },
          { title: id },
        ]}
      />
      <p className="request-detail-description">{detail.description}</p>
      <p className="request-detail-meta">
        {formatWhen(detail.createdAt)}
        {' · '}
        Создатель: {detail.dispatcherLogin}
        {' · '}
        Исполнитель: {detail.technicianLogin}
        {detail.priority != null ? ` · Приоритет: ${detail.priority}` : ''}
      </p>
      <div className="request-detail-header">
        <span className="request-detail-status-label">Текущий статус</span>
        <Select
          className="request-detail-status"
          value={status}
          onChange={setStatus}
          options={STATUSES.map((item) => ({ value: item, label: item }))}
        />
        <Button type="primary" loading={saving} onClick={() => void saveStatus()}>
          Сохранить
        </Button>
      </div>
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
              ref={treeRef}
              className="map-tree"
              blockNode
              treeData={treeData}
              selectedKeys={selectedId == null ? [] : [String(selectedId)]}
              expandedKeys={expandedKeys}
              titleRender={(node) => {
                const current = objects.find((item) => String(item.id) === node.key)
                const tone = mapOwnTone(current)
                return (
                  <span className="map-tree-node">
                    {tone ? <span className={`map-tree-dot map-tree-dot-${tone}`} /> : null}
                    <span className="map-tree-label">{node.title}</span>
                  </span>
                )
              }}
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={(keys) => {
                if (keys.length === 0) {
                  return
                }
                setSelectedId(Number(keys[0]))
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
