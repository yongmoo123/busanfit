import { useEffect, useRef, useState } from 'react'

let sdkPromise

function loadKakaoMaps() {
  if (!sdkPromise) {
    sdkPromise = new Promise((resolve, reject) => {
      const key = import.meta.env.VITE_KAKAO_JS_KEY
      if (!key) {
        reject(new Error('카카오맵 키 설정을 확인해 주세요.'))
        return
      }

      const script = document.createElement('script')
      script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`
      script.onerror = () => reject(new Error('카카오맵을 불러오지 못했어요.'))
      script.onload = () => {
        const maps = window.kakao?.maps
        if (!maps?.load) {
          reject(new Error('카카오맵 앱 설정을 확인해 주세요.'))
          return
        }
        maps.load(() => resolve(maps))
      }
      document.head.appendChild(script)
    })
  }

  return sdkPromise
}

export default function CourseMap({ items, isMock = true }) {
  const mapRef = useRef(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const overlays = []

    loadKakaoMaps()
      .then((maps) => {
        if (!active) return

        const positions = items.map(({ place }) => {
          const { latitude, longitude } = place.coordinates
          return new maps.LatLng(latitude, longitude)
        })

        const map = new maps.Map(mapRef.current, {
          center: positions[0],
          level: 4,
        })

        if (positions.length > 1) {
          const bounds = new maps.LatLngBounds()
          positions.forEach((position) => bounds.extend(position))
          map.setBounds(bounds, 36, 36, 36, 36)

          const line = new maps.Polyline({
            path: positions,
            strokeWeight: 4,
            strokeColor: '#245f53',
            strokeStyle: 'shortdash',
          })
          line.setMap(map)
          overlays.push(line)
        }

        positions.forEach((position, index) => {
          const badge = document.createElement('span')
          badge.className = 'course-map-marker'
          badge.textContent = String(index + 1)
          badge.setAttribute('role', 'img')
          badge.setAttribute('aria-label', `${index + 1}번 방문 장소, ${items[index].place.name}`)

          const marker = new maps.CustomOverlay({
            position,
            content: badge,
            zIndex: 1,
          })
          marker.setMap(map)
          overlays.push(marker)
        })
      })
      .catch(() => {
        if (active) {
          setError('지도를 불러오지 못했어요. 위 타임라인에서 방문 순서를 확인할 수 있어요.')
        }
      })

    return () => {
      active = false
      overlays.forEach((overlay) => overlay.setMap(null))
    }
  }, [items])

  const title = isMock ? '가상 코스 지도' : '코스 지도'

  return (
    <section aria-label={title}>
      <h4>{title}</h4>
      {error ? (
        <p role="status">{error}</p>
      ) : (
        <>
          <p>점선은 방문 순서를 나타내요. 실제 보행 경로는 확인되지 않았어요.</p>
          <div ref={mapRef} style={{ width: '100%', height: 260 }} />
        </>
      )}
    </section>
  )
}
