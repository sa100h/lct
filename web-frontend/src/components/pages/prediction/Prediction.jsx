import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Spin, Tree } from 'antd'
import { AuthHttpError } from '@/api/auth.js'
import { listDispatcherObjects } from '@/api/dispatcherObjects.js'
import { formatForecastStartedMessage, runForecast } from '@/api/forecasts.js'
import { buildObjectTree } from './buildObjectTree.js'
import './Prediction.css'

function runErrorText(error) {
  if (error instanceof AuthHttpError && error.displayMessage) {
    return error.displayMessage
  }
  return 'Не удалось запустить прогноз'
}

export default function Prediction() {
  const [treeData, setTreeData] = useState([])
  const [checkedKeys, setCheckedKeys] = useState([])
  const [allObjects, setAllObjects] = useState(false)
  const [objectsLoading, setObjectsLoading] = useState(true)
  const [objectsError, setObjectsError] = useState(null)
  const [runLoading, setRunLoading] = useState(false)
  const [successText, setSuccessText] = useState(null)
  const [runError, setRunError] = useState(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setObjectsLoading(true)
      setObjectsError(null)
      try {
        const objects = await listDispatcherObjects()
        if (!cancelled) {
          setTreeData(buildObjectTree(objects))
        }
      } catch (error) {
        if (!cancelled) {
          setTreeData([])
          setObjectsError(
            error instanceof AuthHttpError && error.status === 403
              ? 'Нет доступа к списку объектов'
              : 'Не удалось загрузить список объектов',
          )
        }
      } finally {
        if (!cancelled) {
          setObjectsLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const canSubmit = allObjects || checkedKeys.length > 0

  const onRun = async () => {
    setSuccessText(null)
    setRunError(null)
    setRunLoading(true)
    try {
      const result = await runForecast(
        allObjects ? null : checkedKeys.map((key) => Number(key)),
      )
      setSuccessText(formatForecastStartedMessage(result.createdAt))
    } catch (error) {
      setRunError(runErrorText(error))
    } finally {
      setRunLoading(false)
    }
  }

  return (
    <div className="prediction-page">
      <h1>Прогноз</h1>
      {successText ? (
        <Alert className="prediction-alert" type="success" showIcon message={successText} />
      ) : null}
      {runError ? (
        <Alert className="prediction-alert" type="error" showIcon message={runError} />
      ) : null}
      {objectsError ? (
        <Alert className="prediction-alert" type="error" showIcon message={objectsError} />
      ) : null}
      <Checkbox
        checked={allObjects}
        onChange={(event) => setAllObjects(event.target.checked)}
      >
        Все объекты
      </Checkbox>
      <div className="prediction-tree">
        {objectsLoading ? (
          <Spin />
        ) : (
          <Tree
            checkable
            disabled={allObjects}
            treeData={treeData}
            checkedKeys={checkedKeys}
            onCheck={(keys) => setCheckedKeys(Array.isArray(keys) ? keys : keys.checked)}
          />
        )}
      </div>
      <Button
        type="primary"
        loading={runLoading}
        disabled={!canSubmit || runLoading || objectsLoading}
        onClick={() => void onRun()}
      >
        Запустить прогноз
      </Button>
    </div>
  )
}
