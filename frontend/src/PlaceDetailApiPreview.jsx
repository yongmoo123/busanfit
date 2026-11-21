import { useEffect, useState } from 'react'
import PlaceDetail from './PlaceDetail.jsx'
import { createEmptyProfile } from './profile.js'
import { createSession, saveProfile } from './sessionApi.js'

async function getPlaceDetail(placeId, signal) {
  const response = await fetch(`/api/places/${encodeURIComponent(placeId)}`, {
    signal,
  })

  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? '장소를 찾을 수 없어요.'
        : `장소 상세 정보를 불러오지 못했어요. (${response.status})`,
    )
  }

  return response.json()
}

export default function PlaceDetailApiPreview() {
  const [detail, setDetail] = useState(null)
  const [courseItem, setCourseItem] = useState(null)
  const [error, setError] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function loadDetail() {
      try {
        const initialDetail = await getPlaceDetail(
          'synthetic:unknown-detail',
          controller.signal,
        )

        if (!controller.signal.aborted) {
          setDetail(initialDetail)
        }
      } catch (requestError) {
        if (!controller.signal.aborted) {
          setError(requestError.message)
        }
      }
    }

    loadDetail()
    return () => controller.abort()
  }, [])

  async function loadCoursePlace() {
    setError('')
    setIsGenerating(true)

    try {
      const session = await createSession()
      const profile = createEmptyProfile()

      profile.area = {
        value: 'HAEUNDAE',
        source: 'USER',
        strength: 'HARD',
      }

      profile.timeWindow = {
        value: {
          startAt: '2026-11-18T13:00:00+09:00',
          endAt: '2026-11-18T18:00:00+09:00',
        },
        source: 'USER',
        strength: 'HARD',
      }

      const saved = await saveProfile(session.sessionId, profile, 0)

      if (saved.status !== 'READY') {
        throw new Error('코스를 만들기 위한 조건이 준비되지 않았어요.')
      }

      const response = await fetch('/api/courses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId: session.sessionId,
          profileRevision: saved.profileRevision,
        }),
      })

      if (!response.ok) {
        throw new Error(`코스를 만들지 못했어요. (${response.status})`)
      }

      const result = await response.json()
      const firstItem = result.course?.items?.[0]

      if (result.status !== 'SUCCESS' || !firstItem) {
        throw new Error('상세 정보를 확인할 코스 장소가 없어요.')
      }

      const coursePlaceDetail = await getPlaceDetail(firstItem.place.id)
      setDetail(coursePlaceDetail)
      setCourseItem(firstItem)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <main className="place-detail-preview">
      {error && <p role="alert">{error}</p>}

      {!detail && !error && (
        <p role="status">장소 상세 정보를 불러오는 중이에요.</p>
      )}

      {detail && (
        <>
          <button
            type="button"
            onClick={loadCoursePlace}
            disabled={isGenerating}
          >
            {isGenerating ? '가상 코스 만드는 중…' : '가상 코스의 첫 장소 보기'}
          </button>

          <PlaceDetail detail={detail} courseItem={courseItem} isMock />
        </>
      )}
    </main>
  )
}