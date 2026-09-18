import { useCallback, useState } from 'react'
import { Alert, Button, List } from 'antd'
import { MARKERS } from './markers.js'
import YandexMap from './YandexMap.jsx'
import './Map.css'

const MISSING_KEY_TEXT =
  'Не задан ключ Яндекс.Карт (VITE_YANDEX_MAPS_API_KEY). Добавьте его в корневой .env и перезапустите Vite или пересоберите образ.'

const LOAD_ERROR_TEXT =
  'Не удалось загрузить Яндекс.Карты. Проверьте ключ, сеть и ограничения ключа по HTTP Referrer.'

export default function Map() {
  const apikey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
  const [selectedId, setSelectedId] = useState(MARKERS[0].id)
  const [loadError, setLoadError] = useState(false)

  const handleError = useCallback(() => {
    setLoadError(true)
  }, [])

  const showAlert = !apikey || loadError
  const alertText = !apikey ? MISSING_KEY_TEXT : LOAD_ERROR_TEXT

  return (
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
            markers={MARKERS}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onError={handleError}
          />
        )}
      </div>
      <div className="map-page-list">
        <List
          dataSource={MARKERS}
          renderItem={(item) => (
            <List.Item
              className={
                item.id === selectedId ? 'map-list-item map-list-item-active' : 'map-list-item'
              }
              onClick={() => setSelectedId(item.id)}
            >
              <List.Item.Meta title={item.title} description={item.description} />
            </List.Item>
          )}
        />
      </div>
    </div>
  )
}
