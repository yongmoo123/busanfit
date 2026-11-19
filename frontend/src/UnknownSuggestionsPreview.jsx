import { useEffect, useRef, useState } from 'react'
import UnknownPlaceSuggestion from './UnknownPlaceSuggestion.jsx'
import './UnknownSuggestionsPreview.css'

const scenarios = {
  course: '코스 있음 · 미확인 3곳 제외',
  insufficient: '후보 부족 · 미확인 3곳 제외',
  none: '미확인 제외 장소 없음',
  failure: '가상 재생성 실패',
}

export default function UnknownSuggestionsPreview() {
  const [scenario, setScenario] = useState('course')
  const [included, setIncluded] = useState(false)
  const [failNextRequest, setFailNextRequest] = useState(true)
  const [result, setResult] = useState('')

  const resultRef = useRef(null)

  useEffect(() => {
    if (included) resultRef.current?.focus()
  }, [included])

  function reset(nextScenario) {
    setScenario(nextScenario)
    setIncluded(false)
    setFailNextRequest(true)
    setResult('')
  }

  async function regenerate() {
    if (scenario === 'failure' && failNextRequest) {
      setFailNextRequest(false)
      throw new Error('synthetic regeneration failure')
    }
    setIncluded(true)
    setResult('가상 재생성 완료 · 휠체어 조건을 유지하고 미확인 장소를 포함했어요.')
  }

  const showCourse = scenario !== 'insufficient' || included

  return (
    <main className="unknown-preview">
      <h1>정보 없는 장소 포함 제안</h1>
      <p>가상 화면 검증 · 서버 요청과 실제 코스 계산은 수행하지 않습니다.</p>
      <label className="unknown-scenario">
        검증 시나리오
        <select value={scenario} onChange={(event) => reset(event.target.value)}>
          {Object.entries(scenarios).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>

      <section className="unknown-preview-card" aria-label="가상 여행 조건">
        <h2>여행 조건</h2>
        <p>이동제약 · 휠체어 · 직접 입력 · 필수</p>
        <p>미확인 접근성 포함 · {included ? '요청함' : '요청 안 함'}</p>
      </section>

      <p ref={resultRef} role="status" tabIndex={-1}>{result}</p>

      <section className="unknown-preview-card" aria-label="가상 코스 결과">
        <h2>{showCourse ? '가상 코스' : '방문할 장소가 부족해요'}</h2>
        {showCourse ? (
          <ol className="unknown-preview-places">
            <li><strong>[가상] 전시공간 A</strong><p>휠체어 이용 · 확인됨</p></li>
            <li><strong>[가상] 카페 B</strong><p>휠체어 이용 · 확인됨</p></li>
            {included && (
              <li>
                <strong>[가상] 미확인 전시공간 C</strong>
                <p>휠체어 이용 · 정보 없음</p>
                <p className="unknown-place-warning">접근성을 확인하지 못했어요. 방문 전 직접 확인해 주세요.</p>
              </li>
            )}
          </ol>
        ) : <p>현재 조건에서 방문할 장소가 두 곳 미만이에요.</p>}

        {!included && (
          <UnknownPlaceSuggestion
            key={scenario}
            count={scenario === 'none' ? 0 : 3}
            onConfirm={regenerate}
          />
        )}
        {included && <p className="unknown-place-warning">미확인 장소 포함을 요청했어요. 접근성 확인이 필요해요.</p>}
      </section>

      <button className="unknown-reset" type="button" onClick={() => reset(scenario)}>처음 상태로 돌아가기</button>
    </main>
  )
}
