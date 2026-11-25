import { useEffect, useRef, useState } from 'react'
import { groupMapMarkers } from './mapMarkerGroups.js'

let sdkPromise

function loadKakaoMaps() {
  // Reuse the loaded SDK when Vite refreshes this module.
  if (window.kakao?.maps?.Map) return Promise.resolve(window.kakao.maps)
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
    let removeMapListener = () => {}
    let resizeObserver
    let mapContainer
    let initialFrame

    loadKakaoMaps()
      .then((maps) => {
        if (!active) return

        const positions = items.map(({ place }) => {
          const { latitude, longitude } = place.coordinates
          return new maps.LatLng(latitude, longitude)
        })

        if (!mapRef.current || !positions.length) return
        mapContainer = document.createElement('div')
        mapContainer.style.width = '100%'
        mapContainer.style.height = '100%'
        mapRef.current.replaceChildren(mapContainer)
        const map = new maps.Map(mapContainer, {
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

        let markers = []
        const updateMarkers = () => {
          markers.forEach((marker) => marker.setMap(null))
          markers = []
          const projection = map.getProjection()
          const points = positions.map((position) => projection.containerPointFromCoords(position))
          groupMapMarkers(points).forEach(({ x, y, indices }) => {
            const badge = document.createElement('span')
            badge.className = 'course-map-marker'
            badge.textContent = indices.map((index) => index + 1).join(' · ')
            badge.style.width = `${Math.max(28, indices.length * 22)}px`
            badge.style.borderRadius = '999px'
            badge.style.whiteSpace = 'nowrap'
            badge.setAttribute('role', 'img')
            const label = indices.map((index) => `${index + 1}번 방문 장소, ${items[index].place.name}`).join('; ')
            badge.setAttribute('aria-label', label)
            badge.title = label
            const marker = new maps.CustomOverlay({
              position: indices.length === 1 ? positions[indices[0]]
                : projection.coordsFromContainerPoint(new maps.Point(x, y)),
              content: badge,
              zIndex: 1,
            })
            marker.setMap(map)
            markers.push(marker)
          })
        }
        initialFrame = requestAnimationFrame(() => {
          if (!active) return
          map.relayout()
          if (positions.length > 1) {
            const bounds = new maps.LatLngBounds()
            positions.forEach((position) => bounds.extend(position))
            map.setBounds(bounds, 36, 36, 36, 36)
          }
          updateMarkers()
        })
        resizeObserver = new ResizeObserver(() => {
          if (!active || !mapContainer.clientWidth) return
          const center = map.getCenter()
          map.relayout()
          map.setCenter(center)
          updateMarkers()
        })
        resizeObserver.observe(mapContainer)
        maps.event.addListener(map, 'idle', updateMarkers)
        removeMapListener = () => {
          maps.event.removeListener(map, 'idle', updateMarkers)
          markers.forEach((marker) => marker.setMap(null))
        }
      })
      .catch(() => {
        if (active) {
          setError('지도를 불러오지 못했어요. 위 타임라인에서 방문 순서를 확인할 수 있어요.')
        }
      })

    return () => {
      active = false
      cancelAnimationFrame(initialFrame)
      resizeObserver?.disconnect()
      removeMapListener()
      mapContainer?.remove()
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
          <p>가까운 장소는 방문 번호를 함께 표시해요. 지도를 확대하면 구분하기 쉬워요.</p>
          <div ref={mapRef} style={{ width: '100%', height: 260 }} />
        </>
      )}
    </section>
  )
}
