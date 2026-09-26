import { useState } from 'react'
import { useSelector } from 'react-redux'
import HistoryList from '@/components/pages/history/HistoryList.jsx'
import PredictionForm from './PredictionForm.jsx'
import './Prediction.css'

export default function Prediction() {
  const permissions = useSelector((state) => state.auth.permissions)
  const canPredict = permissions.includes('module.prediction')
  const canHistory = permissions.includes('module.history')
  const [refreshKey, setRefreshKey] = useState(0)

  return (
    <div className="prediction-page">
      <h1>Прогноз</h1>
      {canPredict ? (
        <PredictionForm onRan={() => setRefreshKey((key) => key + 1)} />
      ) : null}
      {canHistory ? (
        <>
          <h2>История</h2>
          <HistoryList refreshKey={refreshKey} />
        </>
      ) : null}
    </div>
  )
}
