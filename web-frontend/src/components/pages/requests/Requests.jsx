import { useEffect, useState } from 'react'
import { Alert, Button, Spin, Table, Tag } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { AuthHttpError } from '@/api/auth.js'
import { listRequests } from '@/api/requests.js'
import { requestStatusTagColor } from './requestStatusTag.js'
import './Requests.css'

const EMPTY = 'Нет данных'
const PAGE_SIZE = 20

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

export default function Requests() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const snapshot = await listRequests({ page, pageSize: PAGE_SIZE })
        if (!cancelled) {
          setItems(snapshot.items ?? [])
          setTotal(snapshot.total ?? 0)
        }
      } catch (caught) {
        if (!cancelled) {
          setItems([])
          setTotal(0)
          setError(
            caught instanceof AuthHttpError && caught.status === 403
              ? 'Нет доступа к заявкам'
              : 'Не удалось загрузить заявки',
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
  }, [page])

  if (loading && items.length === 0 && error == null) {
    return <Spin className="requests-spin" />
  }

  return (
    <div className="requests-page">
      {error ? (
        <Alert className="requests-alert" type="error" showIcon message={error} />
      ) : null}
      <Table
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
        }}
        onChange={(pagination) => setPage(pagination.current)}
        onRow={(record) => ({
          onClick: () => navigate(`/requests/${record.id}`),
          className: 'requests-row',
        })}
        locale={{ emptyText: EMPTY }}
        dataSource={items}
        columns={[
          {
            title: 'Дата',
            dataIndex: 'createdAt',
            render: (value) => formatWhen(value),
          },
          { title: 'Описание', dataIndex: 'description' },
          { title: 'Объект', dataIndex: 'objectName' },
          {
            title: 'Статус',
            dataIndex: 'status',
            render: (value) => <Tag color={requestStatusTagColor(value)}>{value}</Tag>,
          },
          { title: 'Создатель', dataIndex: 'dispatcherLogin' },
          { title: 'Исполнитель', dataIndex: 'technicianLogin' },
          {
            title: '',
            key: 'open',
            width: 48,
            align: 'right',
            render: (_, record) => (
              <Button
                type="text"
                icon={<RightOutlined />}
                aria-label="Открыть заявку"
                onClick={() => navigate(`/requests/${record.id}`)}
              />
            ),
          },
        ]}
      />
    </div>
  )
}
