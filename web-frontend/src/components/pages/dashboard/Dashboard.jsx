import { useEffect, useMemo, useState } from 'react'
import { Alert, Spin } from 'antd'
import ReactECharts from 'echarts-for-react'
import { AuthHttpError } from '@/api/auth.js'
import { getDashboard } from '@/api/dashboard.js'
import { FORECAST_STATUS_LABEL } from '@/components/pages/history/forecastStatusTag.js'
import {
  CHART_COLOR,
  FORECAST_STATUS_RANGE,
  OBJECT_TONE_RANGE,
  REQUEST_STATUS_RANGE,
  cartesianOption,
  formatDayLabel,
  hasCounts,
  pieOption,
} from './dashboardCharts.js'
import './Dashboard.css'

const EMPTY = 'Нет данных'
const ECHARTS_STYLE = { height: 260 }

function DashboardSection({ title, children }) {
  return (
    <section className="dashboard-section">
      <h2>{title}</h2>
      <div className="dashboard-card">
        <div className="dashboard-card-body">{children}</div>
      </div>
    </section>
  )
}

function ChartOrEmpty({ empty, children }) {
  if (empty) {
    return <p className="dashboard-empty">{EMPTY}</p>
  }
  return <div className="dashboard-chart">{children}</div>
}

function Chart({ option }) {
  return <ReactECharts option={option} style={ECHARTS_STYLE} notMerge lazyUpdate />
}

function DayBar({ rows, color }) {
  const option = useMemo(
    () =>
      cartesianOption({
        categories: rows.map((row) => formatDayLabel(row.date)),
        values: rows.map((row) => row.count),
        series: { type: 'bar', color },
      }),
    [color, rows],
  )
  return <Chart option={option} />
}

function DayLine({ rows }) {
  const option = useMemo(
    () =>
      cartesianOption({
        categories: rows.map((row) => formatDayLabel(row.date)),
        values: rows.map((row) => row.count),
        series: { type: 'line', color: CHART_COLOR.pending },
      }),
    [rows],
  )
  return <Chart option={option} />
}

function StatusPie({ items, colors, centerLabel }) {
  const option = useMemo(
    () => pieOption({ items, colors, centerLabel }),
    [centerLabel, colors, items],
  )
  return <Chart option={option} />
}

function StatusBar({ items, colors }) {
  const option = useMemo(
    () =>
      cartesianOption({
        categories: items.map((item) => item.name),
        values: items.map((item) => item.count),
        series: { type: 'bar', colors },
      }),
    [colors, items],
  )
  return <Chart option={option} />
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

  const alarmsByDay = data?.alarmsByDay ?? []
  const requestsByDay = data?.requestsByDay ?? []
  const forecastsByStatus = data?.forecastsByStatus ?? []
  const requestPieItems = useMemo(
    () =>
      (data?.requestsByStatus ?? []).map((row) => ({ name: row.status, count: row.count })),
    [data?.requestsByStatus],
  )
  const objectPieItems = useMemo(
    () => [
      { name: 'В норме', count: data?.objects?.normal ?? 0 },
      { name: 'Отклонения', count: data?.objects?.deviation ?? 0 },
    ],
    [data?.objects?.deviation, data?.objects?.normal],
  )
  const forecastBarItems = useMemo(
    () =>
      (data?.forecastsByStatus ?? []).map((row) => ({
        name: FORECAST_STATUS_LABEL[row.status] ?? row.status,
        count: row.count,
      })),
    [data?.forecastsByStatus],
  )

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

  const requestsTotal = data.requestsTotal ?? 0

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

      <div className="dashboard-charts">
        <DashboardSection title="Неисправности за 14 дней">
          <ChartOrEmpty empty={!hasCounts(alarmsByDay)}>
            <DayBar rows={alarmsByDay} color={CHART_COLOR.alarm} />
          </ChartOrEmpty>
        </DashboardSection>

        <DashboardSection title="Заявки">
          <ChartOrEmpty empty={!hasCounts(data.requestsByStatus ?? [])}>
            <StatusPie
              items={requestPieItems}
              colors={REQUEST_STATUS_RANGE}
              centerLabel={`Всего: ${requestsTotal}`}
            />
          </ChartOrEmpty>
        </DashboardSection>

        <DashboardSection title="Заявки по дням">
          <ChartOrEmpty empty={!hasCounts(requestsByDay)}>
            <DayLine rows={requestsByDay} />
          </ChartOrEmpty>
        </DashboardSection>

        <DashboardSection title="Объекты">
          <ChartOrEmpty empty={data.objects.total === 0}>
            <StatusPie items={objectPieItems} colors={OBJECT_TONE_RANGE} />
          </ChartOrEmpty>
        </DashboardSection>

        <DashboardSection title="Прогнозы за 14 дней">
          <ChartOrEmpty empty={!hasCounts(forecastsByStatus)}>
            <StatusBar items={forecastBarItems} colors={FORECAST_STATUS_RANGE} />
          </ChartOrEmpty>
        </DashboardSection>
      </div>
    </div>
  )
}
