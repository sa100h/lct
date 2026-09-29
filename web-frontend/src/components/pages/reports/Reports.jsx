import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, DatePicker, Select } from 'antd'
import dayjs from 'dayjs'
import { getReportPdf } from '@/api/reports.js'
import { REPORT_CATALOG } from './reportCatalog.js'
import { defaultReportRange, isValidReportRange } from './reportPeriod.js'
import './Reports.css'

const LOAD_ERROR = 'Не удалось сформировать отчёт'
const POPUP_ERROR = 'Разрешите всплывающие окна'

export default function Reports() {
  const initial = useMemo(() => defaultReportRange(), [])
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)
  const [code, setCode] = useState(REPORT_CATALOG[0].code)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  const rangeValid = isValidReportRange(from, to)

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      const blob = await getReportPdf(code, from, to)
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
      const url = URL.createObjectURL(blob)
      setPreviewUrl(url)
      const opened = window.open(url, '_blank')
      if (opened == null) {
        setError(POPUP_ERROR)
      }
    } catch {
      setError(LOAD_ERROR)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="reports-page">
      <h1>Отчеты</h1>
      {error ? <Alert type="error" showIcon message={error} /> : null}
      <div className="reports-filters">
        <DatePicker.RangePicker
          value={from && to ? [dayjs(from), dayjs(to)] : null}
          onChange={(dates) => {
            if (!dates?.[0] || !dates?.[1]) {
              setFrom('')
              setTo('')
              return
            }
            setFrom(dates[0].format('YYYY-MM-DD'))
            setTo(dates[1].format('YYYY-MM-DD'))
          }}
        />
        <Select
          className="reports-type"
          value={code}
          onChange={setCode}
          options={REPORT_CATALOG.map((item) => ({
            value: item.code,
            label: item.title,
          }))}
        />
      </div>
      <div className="reports-actions">
        <Button type="primary" disabled={!rangeValid || loading} loading={loading} onClick={() => void generate()}>
          Сформировать
        </Button>
      </div>
    </div>
  )
}
