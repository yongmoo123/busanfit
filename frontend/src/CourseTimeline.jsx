import { useEffect, useId, useState } from 'react'
import CourseMap from './CourseMap.jsx'
import UnknownPlaceSuggestion from './UnknownPlaceSuggestion.jsx'
import { selectCourseSuggestions, includedUnknownPlaceIds } from './unknownInclusion.js'
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

export default function CourseTimeline({
  courseResponse, isMock = !courseResponse, onEditSuggestion, suggestionsDisabled = false, isInjury = false,
  supportsUnknownInclusion = false, onIncludeUnknown, adjustment,
}) {
  const [selectedItemId, setSelectedItemId] = useState(null)
  const detailId = useId()

  const showInsufficient =
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get('qa') === 'course-insufficient'

  const response = courseResponse ?? (showInsufficient ? insufficientExample : courseExample)
  const { status, course, warnings, excludedUnknown } = response
  const suggestions = selectCourseSuggestions(response.suggestions, supportsUnknownInclusion)
  const unknownPlaceIds = includedUnknownPlaceIds(warnings)
  const changedIds = new Set(adjustment?.status === 'SUCCESS'
    ? [...adjustment.changes.timeChangedItemIds, ...adjustment.changes.replacedItems.map((pair) => pair.newItemId)] : [])
  const visibleWarnings = adjustment ? warnings.filter((warning) => !warning.code.startsWith('ADJUSTMENT_')) : warnings
  const controls = (
    <UnknownPlaceSuggestion
      suggestions={suggestions}
      disabled={suggestionsDisabled}
      onConfirm={onIncludeUnknown}
      onEditProfile={(field) => onEditSuggestion?.({ field })}
    />
  )

  if (status === 'INSUFFICIENT_PLACES') {
    return (
      <section className="condition-card" aria-label="후보 부족 안내">
        <h3>방문할 장소가 부족해요</h3>
        {isInjury && !warnings.some((warning) => warning.code === 'INJURY_RULES') && (
          <p className="chat-warning">
            이동이 힘들면 택시·대중교통 이용을 추천해요. 이 코스의 이동시간은 도보 기준이에요.
          </p>
        )}
        {isMock && <p>가상 응답</p>}
        {visibleWarnings.map((warning, index) => (
          <p key={`${warning.code}-${index}`}>{warning.message}</p>
        ))}
        {controls}
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
      {isInjury && !warnings.some((warning) => warning.code === 'INJURY_RULES') && (
        <p className="chat-warning">
          이동이 힘들면 택시·대중교통 이용을 추천해요. 이 코스의 이동시간은 도보 기준이에요.
        </p>
      )}

      {course.validation?.status === 'CONDITIONAL' && (
        <p className="unknown-place-warning">조건부 코스 · 접근성 정보가 없는 장소가 포함돼 있어요. 방문 전 이용 가능 여부를 확인해 주세요.</p>
      )}
      <ol>
        {course.items.map((item) => {
          const incomingLeg = course.legs.find((leg) => leg.toItemId === item.id)

          return (
            <li key={item.id} className={changedIds.has(item.id) ? 'adjustment-item-changed' : undefined}>
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

              {changedIds.has(item.id) && <span className="adjustment-change-badge">변경됨</span>}
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

              {unknownPlaceIds.has(item.place.id) && (
                <p className="unknown-place-warning">접근성 정보 없음 · 이용 가능 여부를 확인하지 못했어요. 방문 전 직접 확인해 주세요.</p>
              )}
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

      {controls}
      {excludedUnknown.count > 0 && (
        <p>정보가 없어 제외된 장소가 {excludedUnknown.count}곳 있어요.</p>
      )}

      {visibleWarnings.map((warning, index) => (
        <p key={`${warning.code}-${index}`}>{warning.message}</p>
      ))}
    </section>
  )
}
