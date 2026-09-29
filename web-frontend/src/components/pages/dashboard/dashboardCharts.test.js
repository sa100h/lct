import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cartesianOption, formatDayLabel, hasCounts, pieOption } from './dashboardCharts.js'

test('hasCounts is false when every count is zero', () => {
  assert.equal(hasCounts([]), false)
  assert.equal(hasCounts([{ count: 0 }, { count: 0 }]), false)
})

test('hasCounts is true when any count is positive', () => {
  assert.equal(hasCounts([{ count: 0 }, { count: 2 }]), true)
})

test('formatDayLabel uses dd.MM', () => {
  assert.equal(formatDayLabel('2026-09-15'), '15.09')
})

test('cartesianOption shows category x and integer y', () => {
  const option = cartesianOption({
    categories: ['15.09', '16.09'],
    values: [1, 0],
    series: { type: 'bar', color: '#ff4d4f' },
  })
  assert.equal(option.xAxis.type, 'category')
  assert.deepEqual(option.xAxis.data, ['15.09', '16.09'])
  assert.equal(option.yAxis.type, 'value')
  assert.equal(option.yAxis.minInterval, 1)
  assert.equal(option.tooltip.trigger, 'axis')
  assert.equal(option.series[0].type, 'bar')
})

test('pieOption maps names and optional center label', () => {
  const option = pieOption({
    items: [
      { name: 'Новая', count: 4 },
      { name: 'В работе', count: 5 },
    ],
    colors: ['#1677ff', '#fa8c16'],
    centerLabel: 'Всего: 9',
  })
  assert.equal(option.tooltip.trigger, 'item')
  assert.equal(option.series[0].type, 'pie')
  assert.equal(option.series[0].data[0].name, 'Новая')
  assert.equal(option.series[0].data[0].value, 4)
  assert.equal(option.title.text, 'Всего: 9')
})

test('pieOption falls back when a color is missing', () => {
  const option = pieOption({
    items: [{ name: 'Отложена', count: 1 }],
    colors: [],
  })
  assert.equal(option.series[0].data[0].itemStyle.color, '#8c8c8c')
})
