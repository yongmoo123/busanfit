import { describeAdjustmentChanges } from './courseAdjustment.js'
import './CourseAdjustment.css'

const formatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const range = (item) => `${formatter.format(new Date(item.startAt))}~${formatter.format(new Date(item.endAt))}`

export default function CourseAdjustmentResult({ response, before, error }) {
  if (error) return <div className="adjustment-preview-error" role="alert"><p>{error}</p></div>
  if (!response || !before) return null
  const changes = response.status === 'SUCCESS'
    ? describeAdjustmentChanges(before, response.course, response.changes) : null
  return (
    <section className="course-adjustment-result" role="status" aria-label="코스 수정 결과">
      <h3>{response.status === 'SUCCESS' ? '수정한 내용' : response.status === 'NEEDS_INPUT'
        ? '추가 확인이 필요해요 · 기존 코스 유지' : '수정을 적용하지 않았어요 · 기존 코스 유지'}</h3>
      {changes?.removed.map((item) => <p key={item.id}>뺀 장소: {item.place.name} (기존 {item.order}번)</p>)}
      {changes?.replaced.map((pair) => <p key={pair.before.id}>바꾼 장소: {pair.before.place.name} → {pair.after.place.name}. 방문 시간은 유지했어요.</p>)}
      {changes?.shifted.map((pair) => <p key={pair.before.id}>{pair.after.place.name}: {range(pair.before)} → {range(pair.after)} · 체류 {pair.before.stayMinutes}분 → {pair.after.stayMinutes}분</p>)}
      {response.status === 'NOT_APPLIED' && response.warnings.filter((warning) => warning.code.startsWith('ADJUSTMENT_')).map((warning, index) => (
        <p key={`${warning.code}-${index}`}>{warning.message}</p>
      ))}
      {response.status === 'NEEDS_INPUT' && <p>아래 수정 입력창의 질문에 답해 주세요. 조건 변경 안내가 나오면 조건 카드에서 변경해 주세요.</p>}
    </section>
  )
}
