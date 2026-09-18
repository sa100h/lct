let loadPromise

export function loadYmaps3(apikey) {
  if (window.ymaps3) {
    return Promise.resolve()
  }
  if (loadPromise) {
    return loadPromise
  }

  loadPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(apikey)}&lang=ru_RU`
    script.async = true
    script.dataset.ymaps3 = 'true'
    script.onload = () => resolve()
    script.onerror = () => {
      loadPromise = undefined
      reject(new Error('Не удалось загрузить Яндекс.Карты'))
    }
    document.head.appendChild(script)
  })

  return loadPromise
}
