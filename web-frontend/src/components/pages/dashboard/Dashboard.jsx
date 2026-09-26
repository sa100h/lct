import { useEffect, useState } from 'react'
import { Alert, Spin, Table } from 'antd'
import { Link } from 'react-router-dom'
import { AuthHttpError } from '@/api/auth.js'
import { getDashboard } from '@/api/dashboard.js'
import './Dashboard.css'

const EMPTY = 'Нет данных'

const FORECAST_STATUS = {
  pending: 'Ожидание',
  running: 'В работе',
  done: 'Готово',
}

function formatWhen(value) {
  return new Date(value).toLocaleString('ru-RU')
}

function DashboardSection({ title, body, children }) {
  return (
    <section className="dashboard-section">
      <h2>{title}</h2>
      <div className={body ? 'dashboard-card' : 'dashboard-card dashboard-card--table'}>
        {body ? <div className="dashboard-card-body">{children}</div> : children}
      </div>
    </section>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const snapshot = await getDashboard()
        if (!cancelled) {
          setData(snapshot)
        }
      } catch (caught) {
        if (!cancelled) {
          setData(null)
          setError(
            caught instanceof AuthHttpError && caught.status === 403
              ? 'Нет доступа к дашборду'
              : 'Не удалось загрузить дашборд',
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
  }, [])

  if (loading) {
    return <Spin className="dashboard-spin" />
  }

  if (error || !data?.objects) {
    return (
      <div className="dashboard-page">
        <h1>Дашборд</h1>
        <Alert
          className="dashboard-alert"
          type="error"
          showIcon
          message={error ?? 'Не удалось загрузить дашборд'}
        />
      </div>
    )
  }

  const problems = data.objects.problemObjects ?? []

  return (
    <div className="dashboard-page">
      <h1>Дашборд</h1>
      <div className="dashboard-metrics">
        <div className="dashboard-metric">
          <span className="dashboard-metric-value">{data.objects.total}</span>
          <span className="dashboard-metric-label">Всего</span>
        </div>
        <div className="dashboard-metric">
          <span className="dashboard-metric-value">{data.objects.normal}</span>
          <span className="dashboard-metric-label">В норме</span>
        </div>
        <div className="dashboard-metric">
          <span className="dashboard-metric-value">{data.objects.deviation}</span>
          <span className="dashboard-metric-label">Отклонения</span>
        </div>
      </div>

      <DashboardSection title="Проблемные объекты" body>
        {problems.length === 0 ? (
          <p className="dashboard-empty">{EMPTY}</p>
        ) : (
          <ul className="dashboard-problems">
            {problems.map((item) => (
              <li key={item.id}>
                <Link to={`/map?object=${item.id}`}>{item.name}</Link>
                {item.statuses?.length > 0 ? ` — ${item.statuses.join(', ')}` : ''}
              </li>
            ))}
          </ul>
        )}
      </DashboardSection>

      <DashboardSection title="События">
        <Table
          pagination={false}
          locale={{ emptyText: EMPTY }}
          rowKey="id"
          dataSource={data.events ?? []}
          columns={[
            {
              title: 'Время',
              dataIndex: 'occurredAt',
              render: (value) => formatWhen(value),
            },
            { title: 'Объект', dataIndex: 'objectName' },
            { title: 'Канал', dataIndex: 'channelName' },
            {
              title: 'Тревога',
              dataIndex: 'isAlarm',
              render: (value) => (value ? 'Тревога' : 'Нет'),
            },
            { title: 'Значение', dataIndex: 'value' },
          ]}
        />
      </DashboardSection>

      <DashboardSection title="Прогнозы">
        <Table
          pagination={false}
          locale={{ emptyText: EMPTY }}
          rowKey="id"
          dataSource={data.forecasts ?? []}
          columns={[
            {
              title: 'Создан',
              dataIndex: 'createdAt',
              render: (value) => formatWhen(value),
            },
            {
              title: 'Статус',
              dataIndex: 'status',
              render: (value) => FORECAST_STATUS[value] ?? value,
            },
          ]}
        />
      </DashboardSection>

      <DashboardSection title="Заявки">
        <Table
          pagination={false}
          locale={{ emptyText: EMPTY }}
          rowKey="id"
          dataSource={data.requests ?? []}
          columns={[
            { title: 'Описание', dataIndex: 'description' },
            { title: 'Объект', dataIndex: 'objectName' },
            { title: 'Статус', dataIndex: 'status' },
          ]}
        />
      </DashboardSection>
    </div>
  )
}
