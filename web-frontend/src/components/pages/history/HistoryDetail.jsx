import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Spin,
  Tree,
  message,
} from 'antd'
import { Link, useParams } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { AuthHttpError } from '@/api/auth.js'
import { getForecastHistory, markForecastErroneous } from '@/api/forecastHistory.js'
import { createRequest } from '@/api/requests.js'
import { listUsersByRole } from '@/api/users.js'
import { buildObjectTree } from '@/components/pages/prediction/buildObjectTree.js'
import { mapForecastTone, mergeExpandedKeys, rootExpandedKeys, scrollTreeToKey, toMapMarkers } from '@/components/pages/map/mapTreeKeys.js'
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

export default function HistoryDetail() {
  const { id } = useParams()
  const apikey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
  const canRequest = useSelector((state) => state.auth.permissions.includes('module.requests'))
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
  const [requestOpen, setRequestOpen] = useState(false)
  const [technicians, setTechnicians] = useState([])
  const [techniciansLoading, setTechniciansLoading] = useState(false)
  const [requestError, setRequestError] = useState(null)
  const [requestSubmitting, setRequestSubmitting] = useState(false)
  const [form] = Form.useForm()
  const treeRef = useRef(null)

  const handleError = useCallback(() => {
    setLoadError(true)
  }, [])

  const applySnapshot = useCallback((snapshot, { keepSelection }) => {
    const list = snapshot.objects ?? []
    const tree = buildObjectTree(list)
    setDetail(snapshot)
    setTreeData(tree)
    setMarkers(toMapMarkers(list, (item) => mapForecastTone(item.hasHighRisk)))
    if (keepSelection) {
      setSelectedId((current) =>
        current != null && list.some((item) => item.id === current)
          ? current
          : tree[0]
            ? Number(tree[0].key)
            : null)
      setModalObject((current) =>
        current == null ? null : (list.find((item) => item.id === current.id) ?? null))
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
      const snapshot = await getForecastHistory(id)
      applySnapshot(snapshot, { keepSelection })
    } catch (caught) {
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

  const openModal = (key) => {
    const object = detail?.objects?.find((item) => String(item.id) === String(key))
    if (object) {
      setModalObject(object)
    }
  }

  const openRequest = async () => {
    setRequestError(null)
    form.resetFields()
    setRequestOpen(true)
    setTechniciansLoading(true)
    try {
      const list = await listUsersByRole('Technics')
      setTechnicians(list)
    } catch {
      setTechnicians([])
      setRequestError('Не удалось загрузить список техников')
    } finally {
      setTechniciansLoading(false)
    }
  }

  const submitRequest = async (values) => {
    setRequestError(null)
    setRequestSubmitting(true)
    try {
      await createRequest({
        forecastJournalId: id,
        dispatcherObjectId: selectedId,
        description: values.description,
        priority: values.priority ?? null,
        technicianId: values.technicianId,
      })
      setRequestOpen(false)
      message.success('Заявка создана')
    } catch (caught) {
      setRequestError(
        caught instanceof AuthHttpError && caught.displayMessage
          ? caught.displayMessage
          : 'Не удалось создать заявку',
      )
    } finally {
      setRequestSubmitting(false)
    }
  }

  const onMarkErroneous = async () => {
    try {
      await markForecastErroneous(id, selectedId)
      message.success('Объекты отмечены как ошибочные')
      await loadDetail({ showSpinner: false, keepSelection: true })
    } catch (caught) {
      message.error(
        caught instanceof AuthHttpError && caught.displayMessage
          ? caught.displayMessage
          : 'Не удалось отметить объекты',
      )
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
  const noSelection = selectedId == null

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
            <div className="history-detail-actions">
              {canRequest ? (
                <Button disabled={noSelection} onClick={() => void openRequest()}>
                  Создать заявку
                </Button>
              ) : null}
              <Popconfirm
                title="Отметить выбранные объекты как ошибочные?"
                okText="Да"
                cancelText="Нет"
                disabled={noSelection}
                onConfirm={() => void onMarkErroneous()}
              >
                <Button disabled={noSelection}>Отметить как ошибочный</Button>
              </Popconfirm>
            </div>
          </div>
          <div className="map-page-list-body">
            <Tree
              ref={treeRef}
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
              titleRender={(node) => {
                const current = objects.find((item) => String(item.id) === node.key)
                const tone = mapForecastTone(current?.hasHighRisk)
                return (
                  <span
                    className="map-tree-node"
                    onDoubleClick={(event) => {
                      event.stopPropagation()
                      openModal(node.key)
                    }}
                  >
                    <span className={`map-tree-dot map-tree-dot-${tone}`} />
                    <span className="map-tree-label">{node.title}</span>
                    {current?.isErroneous ? (
                      <span className="map-tree-erroneous">Помечен как ошибочный</span>
                    ) : null}
                  </span>
                )
              }}
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
            {modalObject.isErroneous ? <p>Помечен как ошибочный</p> : null}
            <p>Результатов прогноза пока нет</p>
          </div>
        ) : null}
      </Modal>
      <Modal
        open={requestOpen}
        title="Создать заявку"
        onCancel={() => setRequestOpen(false)}
        footer={null}
        destroyOnHidden
      >
        {requestError ? <Alert type="error" showIcon message={requestError} /> : null}
        <Form form={form} layout="vertical" onFinish={(values) => void submitRequest(values)}>
          <Form.Item
            label="Описание"
            name="description"
            rules={[{ required: true, message: 'Введите описание' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="Приоритет" name="priority">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            label="Техник"
            name="technicianId"
            rules={[{ required: true, message: 'Выберите техника' }]}
          >
            <Select
              loading={techniciansLoading}
              disabled={technicians.length === 0}
              options={technicians.map((item) => ({ value: item.id, label: item.login }))}
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={requestSubmitting}
            disabled={technicians.length === 0}
          >
            Создать
          </Button>
        </Form>
      </Modal>
    </div>
  )
}
