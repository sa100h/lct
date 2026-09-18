import { useEffect, useMemo, useState } from 'react'
import React from 'react'
import ReactDOM from 'react-dom'
import { loadYmaps3 } from './loadYmaps3.js'

const SCHEME_WITHOUT_POI = [
  {
    tags: { any: ['poi'] },
    stylers: [{ visibility: 'off' }],
  },
]

export default function YandexMap({ apikey, markers, selectedId, onSelect, onError }) {
  const [mapApi, setMapApi] = useState(null)
  const selected = useMemo(
    () => markers.find((item) => item.id === selectedId) ?? markers[0],
    [markers, selectedId],
  )

  useEffect(() => {
    let cancelled = false

    const init = async () => {
      try {
        await loadYmaps3(apikey)
        await window.ymaps3.ready
        const ymaps3React = await window.ymaps3.import('@yandex/ymaps3-reactify')
        const reactify = ymaps3React.reactify.bindTo(React, ReactDOM)
        const { YMap, YMapDefaultSchemeLayer, YMapMarker } = reactify.module(window.ymaps3)
        if (!cancelled) {
          setMapApi({ YMap, YMapDefaultSchemeLayer, YMapMarker })
        }
      } catch {
        if (!cancelled) {
          onError()
        }
      }
    }

    init()
    return () => {
      cancelled = true
    }
  }, [apikey, onError])

  if (!mapApi) {
    return <div className="map-canvas" />
  }

  const { YMap, YMapDefaultSchemeLayer, YMapMarker } = mapApi

  return (
    <div className="map-canvas">
      <YMap location={{ center: selected.coordinates, zoom: 11 }}>
        <YMapDefaultSchemeLayer customization={SCHEME_WITHOUT_POI} />
        {markers.map((marker) => (
          <YMapMarker key={marker.id} coordinates={marker.coordinates}>
            <button
              type="button"
              className={
                marker.id === selectedId ? 'map-marker map-marker-active' : 'map-marker'
              }
              onClick={() => onSelect(marker.id)}
            />
          </YMapMarker>
        ))}
      </YMap>
    </div>
  )
}
