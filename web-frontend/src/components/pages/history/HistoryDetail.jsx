import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Spin,
  Tag,
  Tree,
  message,
} from 'antd'
import { Link, useParams } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { AuthHttpError } from '@/api/auth.js'
import {
  approveForecast,
  getForecastHistory,
  markForecastErroneous,
} from '@/api/forecastHistory.js'
import { createRequest } from '@/api/requests.js'
import { listUsersByRole } from '@/api/users.js'
import { buildObjectTree } from '@/components/pages/prediction/buildObjectTree.js'
import { mapForecastTone, mergeExpandedKeys, rootExpandedKeys, scrollTreeToKey, toMapMarkers } from '@/components/pages/map/mapTreeKeys.js'
import { formatObjectCount } from '@/components/objectTree/formatObjectCount.js'
import { forecastCategoryLabel, forecastResultHeadline, formatForecastValueList } from '@/components/pages/history/forecastResultCopy.js'
import { FORECAST_STATUS_LABEL, forecastStatusTagColor } from '@/components/pages/history/forecastStatusTag.js'
import HistoryObjectCheckTree from '@/components/pages/history/HistoryObjectCheckTree.jsx'
import YandexMap from '@/components/pages/map/YandexMap.jsx'
import '@/components/pages/map/Map.css'
import './HistoryDetail.css'

const MISSING_KEY_TEXT =
  'Не задан ключ Яндекс.Карт (VITE_YANDEX_MAPS_API_KEY). Добавьте его в корневой .env и перезапустите Vite или пересоберите образ.'

const LOAD_ERROR_TEXT =
  'Не удалось загрузить Яндекс.Карты. Проверьте ключ, сеть и ограничения ключа по HTTP Referrer.'

const HISTORY_MODAL_STYLE = { top: 24 }

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

function keysToIds(keys) {
  return keys.map((key) => Number(key))
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
  const [requestKeys, setRequestKeys] = useState([])
  const [technicians, setTechnicians] = useState([])
  const [techniciansLoading, setTechniciansLoading] = useState(false)
  const [requestError, setRequestError] = useState(null)
  const [requestSubmitting, setRequestSubmitting] = useState(false)
  const [erroneousOpen, setErroneousOpen] = useState(false)
  const [erroneousKeys, setErroneousKeys] = useState([])
  const [erroneousError, setErroneousError] = useState(null)
  const [erroneousSubmitting, setErroneousSubmitting] = useState(false)
  const [approveOpen, setApproveOpen] = useState(false)
  const [approveError, setApproveError] = useState(null)
  const [approveSubmitting, setApproveSubmitting] = useState(false)
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
    setRequestKeys([])
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
    if (requestKeys.length === 0) {
      return
    }
    setRequestError(null)
    setRequestSubmitting(true)
    try {
      await createRequest({
        forecastJournalId: id,
        dispatcherObjectIds: keysToIds(requestKeys),
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

  const submitErroneous = async () => {
    if (erroneousKeys.length === 0) {
      throw new Error('empty')
    }
    setErroneousError(null)
    setErroneousSubmitting(true)
    try {
      await markForecastErroneous(id, keysToIds(erroneousKeys))
      setErroneousOpen(false)
      message.success('Объекты отмечены как ошибочные')
      await loadDetail({ showSpinner: false, keepSelection: true })
    } catch (caught) {
      setErroneousError(
        caught instanceof AuthHttpError && caught.displayMessage
          ? caught.displayMessage
          : 'Не удалось отметить объекты',
      )
      throw caught
    } finally {
      setErroneousSubmitting(false)
    }
  }

  const submitApprove = async () => {
    setApproveError(null)
    setApproveSubmitting(true)
    try {
      await approveForecast(id)
      setApproveOpen(false)
      message.success('Прогноз обработан')
      await loadDetail({ showSpinner: false, keepSelection: true })
    } catch (caught) {
      setApproveError(
        caught instanceof AuthHttpError && caught.displayMessage
          ? caught.displayMessage
          : 'Не удалось обработать прогноз',
      )
      throw caught
    } finally {
      setApproveSubmitting(false)
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
  const formattedForecastValues = formatForecastValueList(modalObject?.forecastValues)

  return (
    <div className="history-detail">
      <div className="history-detail-header">
        <div className="history-detail-header-start">
          <Breadcrumb
            items={[
              { title: <Link to="/prediction">Прогноз</Link> },
              { title: `Прогноз ${formatWhen(detail.createdAt)}` },
            ]}
          />
          <Tag color={forecastStatusTagColor(detail.status)}>
            {FORECAST_STATUS_LABEL[detail.status] ?? detail.status}
          </Tag>
        </div>
        <div className="history-detail-actions">
          {canRequest ? (
            <Button onClick={() => void openRequest()}>Создать заявку</Button>
          ) : null}
          <Button
            onClick={() => {
              setErroneousError(null)
              setErroneousKeys([])
              setErroneousOpen(true)
            }}
          >
            Отметить как ошибочный
          </Button>
          {detail.status === 'done' ? (
            <Button
              onClick={() => {
                setApproveError(null)
                setApproveOpen(true)
              }}
            >
              Прогноз обработан
            </Button>
          ) : null}
        </div>
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
        style={HISTORY_MODAL_STYLE}
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
            <p>{forecastResultHeadline(modalObject)}</p>
            {formattedForecastValues.length > 0 ? (
              <ul>
                {formattedForecastValues.map((item) => (
                  <li key={`${item.channelId}-${item.category}`}>
                    {item.displayLabel} — {forecastCategoryLabel(item.category)}: {item.displayValue}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </Modal>
      <Modal
        open={requestOpen}
        title="Создать заявку"
        onCancel={() => setRequestOpen(false)}
        footer={null}
        destroyOnHidden
        style={HISTORY_MODAL_STYLE}
      >
        {requestError ? <Alert type="error" showIcon message={requestError} /> : null}
        <Form form={form} layout="vertical" onFinish={(values) => void submitRequest(values)}>
          <Form.Item label="Объекты" required>
            <div className="history-detail-check-tree">
              <HistoryObjectCheckTree
                treeData={treeData}
                checkedKeys={requestKeys}
                onCheck={setRequestKeys}
              />
            </div>
          </Form.Item>
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
            disabled={requestKeys.length === 0 || technicians.length === 0}
          >
            Создать
          </Button>
        </Form>
      </Modal>
      <Modal
        open={erroneousOpen}
        title="Отметить как ошибочный"
        okText="Да"
        cancelText="Нет"
        confirmLoading={erroneousSubmitting}
        okButtonProps={{ disabled: erroneousKeys.length === 0 }}
        onOk={() => void submitErroneous()}
        onCancel={() => setErroneousOpen(false)}
        destroyOnHidden
        style={HISTORY_MODAL_STYLE}
      >
        {erroneousError ? <Alert type="error" showIcon message={erroneousError} /> : null}
        <div className="history-detail-check-tree">
          <HistoryObjectCheckTree
            treeData={treeData}
            checkedKeys={erroneousKeys}
            onCheck={setErroneousKeys}
          />
        </div>
      </Modal>
      <Modal
        open={approveOpen}
        title="Прогноз обработан"
        okText="Да"
        cancelText="Нет"
        confirmLoading={approveSubmitting}
        onOk={() => void submitApprove()}
        onCancel={() => setApproveOpen(false)}
        destroyOnHidden
        style={HISTORY_MODAL_STYLE}
      >
        {approveError ? <Alert type="error" showIcon message={approveError} /> : null}
        <p>Отметить прогноз как обработанный?</p>
      </Modal>
    </div>
  )
}
