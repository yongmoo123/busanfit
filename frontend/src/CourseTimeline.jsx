import CourseMap from './CourseMap.jsx'
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

export default function CourseTimeline() {
  const showInsufficient = import.meta.env.DEV
    && new URLSearchParams(window.location.search).get('qa') === 'course-insufficient'
  const response = showInsufficient ? insufficientExample : courseExample
  const { status, course, warnings, excludedUnknown } = response

  if (status === 'INSUFFICIENT_PLACES') {
    return (
      <section className="condition-card" aria-label="가상 후보 부족 안내">
        <h3>방문할 장소가 부족해요</h3>
        <p>가상 응답</p>
        {warnings.map((warning) => (
          <p key={warning.code}>{warning.message}</p>
        ))}
        {excludedUnknown.count > 0 && (
          <p>필요한 정보가 없어 제외된 장소 {excludedUnknown.count}곳</p>
        )}
      </section>
    )
  }

  return (
    <section className="condition-card" aria-label="가상 코스 타임라인">
      <h3>가상 코스 타임라인</h3>
      <ol>
        {course.items.map((item) => {
          const incomingLeg = course.legs.find(
            (leg) => leg.toItemId === item.id,
          )

          return (
            <li key={item.id}>
              <strong>{item.place.name}</strong>
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
                {' · 체류 '}{item.stayMinutes}분
              </p>
              <p>
                접근성 등급:{' '}
                {accessibilityLabels[item.place.accessibility?.grade] ?? '정보 없음'}
              </p>
            </li>
          )
        })}
      </ol>
      <CourseMap items={course.items} />
      {warnings.map((warning) => (
        <p key={warning.code}>{warning.message}</p>
      ))}
    </section>
  )
}