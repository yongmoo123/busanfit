import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import PlaceDetail from './PlaceDetail.jsx'
import PlaceDetailApiPreview from './PlaceDetailApiPreview.jsx'
import placeDetailMock from './mocks/05-place.response.json'

const previewCourseItem = {
  stayMinutes: 60,
  reason: '실내 전시공간으로 실내 위주 선호에 부합합니다.',
}

const qa = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get('qa')
  : null

let page = <App />

if (qa === 'place-detail-api') {
  page = <PlaceDetailApiPreview />
} else if (qa === 'place-detail') {
  page = (
    <main className="place-detail-preview">
      <PlaceDetail
        detail={placeDetailMock}
        courseItem={previewCourseItem}
        isMock
      />
    </main>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>{page}</StrictMode>,
)