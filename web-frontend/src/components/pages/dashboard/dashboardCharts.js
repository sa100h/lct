export const CHART_COLOR = {
  pending: '#1677ff',
  running: '#fa8c16',
  done: '#52c41a',
  Новая: '#1677ff',
  'В работе': '#fa8c16',
  Закрыта: '#52c41a',
  normal: '#52c41a',
  deviation: '#ff4d4f',
  alarm: '#ff4d4f',
}

export const REQUEST_STATUS_DOMAIN = ['Новая', 'В работе', 'Закрыта']
export const REQUEST_STATUS_RANGE = [
  CHART_COLOR.Новая,
  CHART_COLOR['В работе'],
  CHART_COLOR.Закрыта,
]

export const FORECAST_STATUS_DOMAIN = ['Ожидание', 'В работе', 'Готово']
export const FORECAST_STATUS_RANGE = [
  CHART_COLOR.pending,
  CHART_COLOR.running,
  CHART_COLOR.done,
]

export const OBJECT_TONE_DOMAIN = ['В норме', 'Отклонения']
export const OBJECT_TONE_RANGE = [CHART_COLOR.normal, CHART_COLOR.deviation]

const AXIS_LABEL = { color: '#6b7280', fontSize: 11 }

export function cartesianOption({ categories, values, series }) {
  const isLine = series.type === 'line'
  const barData = series.colors
    ? values.map((value, index) => ({
        value,
        itemStyle: {
          color: series.colors[index],
          borderRadius: [6, 6, 0, 0],
        },
      }))
    : values

  return {
    grid: { left: 8, right: 12, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: categories,
      axisTick: { alignWithLabel: true },
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: AXIS_LABEL,
    },
    series: [
      isLine
        ? {
            type: 'line',
            data: values,
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            itemStyle: { color: series.color },
            lineStyle: { width: 2, color: series.color },
            areaStyle: { color: series.color, opacity: 0.12 },
          }
        : {
            type: 'bar',
            data: barData,
            barMaxWidth: 28,
            itemStyle: series.colors
              ? undefined
              : { color: series.color, borderRadius: [6, 6, 0, 0] },
          },
    ],
  }
}

export function pieOption({ items, colors, centerLabel }) {
  return {
    tooltip: { trigger: 'item' },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      textStyle: { color: '#374151' },
    },
    title: centerLabel
      ? {
          text: centerLabel,
          left: '36%',
          top: 'center',
          textAlign: 'center',
          textStyle: { fontSize: 16, fontWeight: 600, color: '#111827' },
        }
      : undefined,
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['38%', '50%'],
        label: { show: false },
        data: items.map((item, index) => ({
          name: item.name,
          value: item.count,
          itemStyle: { color: colors[index] },
        })),
      },
    ],
  }
}

export function hasCounts(rows) {
  return rows.some((row) => row.count > 0)
}

export function formatDayLabel(date) {
  const parts = date.split('-')
  return `${parts[2]}.${parts[1]}`
}
