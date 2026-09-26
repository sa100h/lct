import { useEffect, useState } from 'react'
import { Alert, Button, DatePicker, Select, Spin, Table } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { AuthHttpError } from '@/api/auth.js'
import { listForecastAuthors, listForecastHistory } from '@/api/forecastHistory.js'
import './History.css'

const EMPTY = 'Нет данных'
const PAGE_SIZE = 20

const FORECAST_STATUS = {
  pending: 'Ожидание',
  running: 'В работе',
  done: 'Готово',
}

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

export default function HistoryList({ refreshKey = 0 }) {
  const navigate = useNavigate()
  const [authors, setAuthors] = useState([])
  const [createdBy, setCreatedBy] = useState(null)
  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    const loadAuthors = async () => {
      try {
        const list = await listForecastAuthors()
        if (!cancelled) {
          setAuthors(list)
        }
      } catch {
        if (!cancelled) {
          setAuthors([])
        }
      }
    }

    void loadAuthors()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const snapshot = await listForecastHistory({
          createdBy,
          from,
          to,
          page,
          pageSize: PAGE_SIZE,
        })
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
              ? 'Нет доступа к истории'
              : 'Не удалось загрузить историю',
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
  }, [createdBy, from, to, page, refreshKey])

  if (loading && items.length === 0 && error == null) {
    return <Spin className="history-spin" />
  }

  return (
    <div className="history-page">
      {error ? (
        <Alert className="history-alert" type="error" showIcon message={error} />
      ) : null}
      <div className="history-filters">
        <Select
          allowClear
          placeholder="Все"
          className="history-filter-author"
          value={createdBy}
          onChange={(value) => {
            setCreatedBy(value ?? null)
            setPage(1)
          }}
          options={authors.map((author) => ({
            value: author.id,
            label: author.login,
          }))}
        />
        <DatePicker.RangePicker
          onChange={(dates) => {
            if (!dates?.[0] || !dates?.[1]) {
              setFrom(null)
              setTo(null)
            } else {
              setFrom(dates[0].format('YYYY-MM-DD'))
              setTo(dates[1].format('YYYY-MM-DD'))
            }
            setPage(1)
          }}
        />
      </div>
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
        locale={{ emptyText: EMPTY }}
        dataSource={items}
        columns={[
          {
            title: 'Дата',
            dataIndex: 'createdAt',
            render: (value) => formatWhen(value),
          },
          { title: 'Автор', dataIndex: 'authorLogin' },
          {
            title: 'Статус',
            dataIndex: 'status',
            render: (value) => FORECAST_STATUS[value] ?? value,
          },
          { title: 'Объекты', dataIndex: 'objectCount' },
          {
            title: '',
            key: 'open',
            width: 48,
            align: 'right',
            render: (_, record) => (
              <Button
                type="text"
                icon={<RightOutlined />}
                aria-label="Открыть прогноз"
                onClick={() => navigate(`/history/${record.id}`)}
              />
            ),
          },
        ]}
      />
    </div>
  )
}
