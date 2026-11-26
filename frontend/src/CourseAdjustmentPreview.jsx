import { useRef, useState } from 'react'
import CourseAdjustmentPanel from './CourseAdjustmentPanel.jsx'
import { acceptAdjustmentResponse, describeAdjustmentChanges, adjustmentErrorMessage } from './courseAdjustment.js'
import { adjustmentScenarios, initialPreviewCourse, simulateAdjustment } from './courseAdjustmentPreviewData.js'
import './CourseAdjustment.css'

const formatTime = (value) => new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).format(new Date(value))
const timeRange = (item) => `${formatTime(item.startAt)}~${formatTime(item.endAt)}`

function AdjustmentScenario({ scenario }) {
  const [course, setCourse] = useState(initialPreviewCourse)
  const [result, setResult] = useState(null)
  const [previous, setPrevious] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recoveryRequired, setRecoveryRequired] = useState(false)
  const [requests, setRequests] = useState(0)
  const activeRequest = useRef(false)
  const mountedGeneration = useRef(0)
  const latest = useRef(course)

  async function submit(message) {
    if (activeRequest.current || recoveryRequired) return false
    activeRequest.current = true
    const generation = mountedGeneration.current
    const original = latest.current
    const nextRequest = requests + 1
    setBusy(true)
    setError('')
    setRequests(nextRequest)
    try {
      // A mock delay exposes busy/duplicate controls. This never calls the API.
      await new Promise((resolve) => setTimeout(resolve, 650))
      if (generation !== mountedGeneration.current) return false
      const response = simulateAdjustment(scenario, original, nextRequest, message)
      const applied = acceptAdjustmentResponse(latest.current, original.id, original.profileRevision, response)
      if (applied.ignored) return false
      setPrevious(original)
      setResult(response)
      latest.current = applied.course
      setCourse(applied.course)
      return true
    } catch (requestError) {
      if (generation !== mountedGeneration.current) return false
      setError(adjustmentErrorMessage(requestError))
      setResult(null)
      setRecoveryRequired(true)
      return false
    } finally {
      if (generation === mountedGeneration.current) {
        activeRequest.current = false
        setBusy(false)
      }
    }
  }

  const changes = result?.status === 'SUCCESS' && previous
    ? describeAdjustmentChanges(previous, course, result.changes) : null
  const changedIds = new Set(result?.status === 'SUCCESS'
    ? [...result.changes.timeChangedItemIds, ...result.changes.replacedItems.map((pair) => pair.newItemId)] : [])
  const [panelVersion, setPanelVersion] = useState(0)
  function reset() {
    mountedGeneration.current += 1
    activeRequest.current = false
    const initial = initialPreviewCourse()
    latest.current = initial
    setCourse(initial)
    setPrevious(null)
    setResult(null)
    setError('')
    setRecoveryRequired(false)
    setBusy(false)
    setRequests(0)
    setPanelVersion((version) => version + 1)
  }

  return (
    <>
      <p className="adjustment-preview-help">이 시나리오 입력 예: {adjustmentScenarios.find(([key]) => key === scenario)[2]}</p>
      <section className="adjustment-preview-card" aria-label="현재 가상 코스">
        <h2>가상 코스 타임라인</h2>
        <p>13:00~18:00 · 도보 · 이동제약 없음 · 가상 장소 3곳으로 시작해요.</p>
        <ol className="adjustment-preview-timeline">
          {course.items.map((item) => (
            <li key={item.id} className={changedIds.has(item.id) ? 'adjustment-item-changed' : ''}>
              <strong>{item.place.name}</strong>
              {changedIds.has(item.id) && <span className="adjustment-change-badge">변경됨</span>}
              <p>{timeRange(item)} · 체류 {item.stayMinutes}분</p>
              {course.legs.filter((leg) => leg.toItemId === item.id).map((leg) => (
                <p key={leg.fromItemId}>이전 장소에서 도보 {leg.minutes}분 (가상 추정)</p>
              ))}
            </li>
          ))}
        </ol>
      </section>

      {result && (
        <section className="adjustment-preview-card adjustment-outcome" role="status" aria-label="수정 결과">
          <h2>{result.status === 'SUCCESS' ? '코스를 수정했어요' : result.status === 'NEEDS_INPUT'
            ? '추가 확인이 필요해요 · 기존 코스 유지' : '수정을 적용하지 않았어요 · 기존 코스 유지'}</h2>
          {changes?.removed.map((item) => <p key={item.id}>뺀 장소: {item.place.name} (기존 {item.order}번)</p>)}
          {changes?.replaced.map((pair) => <p key={pair.before.id}>바꾼 장소: {pair.before.place.name} → {pair.after.place.name}. 방문 시간은 유지했어요.</p>)}
          {changes?.shifted.map((pair) => <p key={pair.before.id}>{pair.after.place.name}: {timeRange(pair.before)} → {timeRange(pair.after)} · 체류 {pair.before.stayMinutes}분 → {pair.after.stayMinutes}분</p>)}
          {result.warnings.filter((warning) => warning.code.startsWith('ADJUSTMENT_')).map((warning) => (
            <p key={warning.code}>{warning.message}</p>
          ))}
          {result.status === 'NEEDS_INPUT' && <p>아직 수정하지 않았어요. 아래 질문에 답해 주세요.</p>}
        </section>
      )}
      {error && <div className="adjustment-preview-error" role="alert"><p>{error}</p><p>기존 코스는 유지했어요.</p></div>}
      <CourseAdjustmentPanel key={panelVersion} onSubmit={submit} busy={busy}
        disabled={recoveryRequired} questions={result?.questions ?? []} />
      <button className="adjustment-preview-reset" type="button" onClick={reset}>처음 상태로 돌아가기</button>
      <details className="adjustment-preview-metadata">
        <summary>가상 동작 확인 정보</summary>
        <p>모의 요청 횟수: {requests}회 · 실제 서버 요청: 0회</p>
        <p>현재 courseId: {course.id}</p>
        <p>profileRevision: {course.profileRevision} (수정 후에도 유지)</p>
        <p>입력 해석은 수행하지 않아요. 선택한 시나리오가 결과를 결정해요.</p>
      </details>
    </>
  )
}

export default function CourseAdjustmentPreview() {
  const [scenario, setScenario] = useState('remove')
  return (
    <main className="course-adjustment-preview">
      <h1>대화형 코스 수정 · 가상 화면</h1>
      <p>서버 계약 초안 기준 화면 검증용이에요. 실제 API·LLM·DB 요청은 보내지 않아요. 일반 코스 수정 기능은 아직 비활성이에요.</p>
      <label className="adjustment-scenario">검증 시나리오
        <select value={scenario} onChange={(event) => setScenario(event.target.value)}>
          {adjustmentScenarios.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <AdjustmentScenario key={scenario} scenario={scenario} />
    </main>
  )
}
