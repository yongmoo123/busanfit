import { useEffect, useId, useState } from 'react'
import CourseMap from './CourseMap.jsx'
import PlaceDetail from './PlaceDetail.jsx'
import { getPlaceDetail } from './courseApi.js'
import courseExample from './mocks/04-course.success.response.json'
import insufficientExample from './mocks/04-course.insufficient.response.json'

const accessibilityLabels = {
  VERIFIED: '확인됨',
  UNKNOWN: '정보 없음',
  UNSUITABLE: '부적합',
}

const timeFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function formatTime(value) {
  return timeFormatter.format(new Date(value))
}

function ServerPlaceDetail({ item, isMock }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const placeId = item.place.id

  useEffect(() => {
    const controller = new AbortController()

    async function loadDetail() {
      try {
        const response = await getPlaceDetail(placeId, controller.signal)
        if (!controller.signal.aborted) setDetail(response)
      } catch (requestError) {
        if (!controller.signal.aborted) {
          setError(
            requestError.status === 404
              ? '장소를 찾을 수 없어요.'
              : '장소 상세 정보를 불러오지 못했어요. 상세 보기를 닫았다가 다시 열어 주세요.',
          )
        }
      }
    }

    loadDetail()
    return () => controller.abort()
  }, [placeId])

  if (error) return <p role="alert">{error}</p>
  if (!detail) return <p role="status">장소 상세 정보를 불러오는 중이에요.</p>

  return <PlaceDetail detail={detail} courseItem={item} isMock={isMock} />
}

export default function CourseTimeline({ courseResponse, isMock = !courseResponse }) {
  const [selectedItemId, setSelectedItemId] = useState(null)
  const detailId = useId()

  const showInsufficient =
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get('qa') === 'course-insufficient'

  const response = courseResponse ?? (showInsufficient ? insufficientExample : courseExample)
  const { status, course, warnings, excludedUnknown } = response

  if (status === 'INSUFFICIENT_PLACES') {
    return (
      <section className="condition-card" aria-label="후보 부족 안내">
        <h3>방문할 장소가 부족해요</h3>
        {isMock && <p>가상 응답</p>}
        {warnings.map((warning) => (
          <p key={warning.code}>{warning.message}</p>
        ))}
        {excludedUnknown.count > 0 && (
          <p>필요한 정보가 없어 제외된 장소 {excludedUnknown.count}곳</p>
        )}
      </section>
    )
  }

  const selectedItem = course.items.find((item) => item.id === selectedItemId)
  const title = isMock ? '가상 코스 타임라인' : '코스 타임라인'

  return (
    <section className="condition-card" aria-label={title}>
      <h3>{title}</h3>

      <ol>
        {course.items.map((item) => {
          const incomingLeg = course.legs.find((leg) => leg.toItemId === item.id)

          return (
            <li key={item.id}>
              <button
                type="button"
                className="profile-secondary"
                aria-expanded={selectedItemId === item.id}
                aria-controls={detailId}
                onClick={() =>
                  setSelectedItemId((currentId) =>
                    currentId === item.id ? null : item.id,
                  )
                }
              >
                {item.place.name} 상세 보기
              </button>

              {incomingLeg && (
                <p>
                  이전 장소에서 이동 {incomingLeg.minutes}분
                  {incomingLeg.isEstimate && ' (추정)'}
                </p>
              )}

              <p>
                <time dateTime={item.startAt}>{formatTime(item.startAt)}</time>
                {' ~ '}
                <time dateTime={item.endAt}>{formatTime(item.endAt)}</time>
                {' · 체류 '}
                {item.stayMinutes}분
              </p>

              <p>
                접근성 등급:{' '}
                {accessibilityLabels[item.place.accessibility?.grade] ?? '정보 없음'}
              </p>
            </li>
          )
        })}
      </ol>

      <div id={detailId} hidden={!selectedItem}>
        {selectedItem && (
          courseResponse ? (
            <ServerPlaceDetail
              key={selectedItem.id}
              item={selectedItem}
              isMock={isMock}
            />
          ) : (
            <PlaceDetail
              detail={{
                place: selectedItem.place,
                sources: course.sources.filter((source) =>
                  selectedItem.place.sourceIds.includes(source.id),
                ),
                warnings: [],
              }}
              courseItem={selectedItem}
              isMock
            />
          )
        )}
      </div>

      <CourseMap items={course.items} isMock={isMock} />

      {warnings.map((warning) => (
        <p key={warning.code}>{warning.message}</p>
      ))}
    </section>
  )
}