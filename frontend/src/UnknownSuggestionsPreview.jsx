import { useEffect, useRef, useState } from 'react'
import UnknownPlaceSuggestion from './UnknownPlaceSuggestion.jsx'
import courseExample from './mocks/04-course.success.response.json'
import profileExample from './mocks/02-chat.ready.response.json'
import {
  createPreviewFlow,
  simulatePreviewAcceptance,
  simulatePreviewCourse,
  simulatePreviewSave,
} from './unknownPreviewFlow.js'
import './UnknownSuggestionsPreview.css'

const scenarios = {
  course: '코스 있음 · 미확인 3곳 제외',
  insufficient: '후보 부족 · course=null · 포함 칩',
  twoDefaults: '기본값 칩 2개 + 포함 칩 1개',
  multiple: '휠체어·유모차 복수 제약',
  none: '포함 가능한 미확인 후보 없음',
  saveFailure: '가상 프로필 저장 실패',
  needsInput: '가상 저장 응답 NEEDS_INPUT',
  failure: '가상 저장 성공 후 코스 생성 실패',
}

function initialFlow(scenario) {
  return createPreviewFlow(scenario, courseExample, profileExample.profile)
}

export default function UnknownSuggestionsPreview() {
  const [scenario, setScenario] = useState('course')
  const [flow, setFlow] = useState(() => initialFlow('course'))
  const [editingField, setEditingField] = useState(null)
  const resultRef = useRef(null)
  const transportRef = useRef(null)
  const mobilityRef = useRef(null)

  useEffect(() => {
    if (flow.outcome === 'GENERATED') resultRef.current?.focus()
  }, [flow.outcome])

  useEffect(() => {
    if (editingField === 'transport') transportRef.current?.focus()
    if (editingField === 'mobility') mobilityRef.current?.focus()
  }, [editingField])

  function reset(nextScenario) {
    setScenario(nextScenario)
    setFlow(initialFlow(nextScenario))
    setEditingField(null)
  }

  function savePreviewProfile(profile) {
    setFlow(simulatePreviewSave(flow, profile, scenario))
    setEditingField(null)
  }

  function changeMobility(value) {
    savePreviewProfile({
      ...flow.profile,
      mobility: { value, source: 'USER', strength: 'HARD' },
    })
  }

  function applyInfantDefault() {
    savePreviewProfile({
      ...flow.profile,
      companions: {
        value: { type: 'FAMILY', count: 3, hasInfant: true },
        source: 'USER', strength: 'SOFT',
      },
      mobility: { value: null, source: 'UNSET', strength: 'HARD' },
    })
  }

  async function acceptInclusion() {
    const next = simulatePreviewAcceptance(flow, scenario)
    setFlow(next)
    if (next.outcome !== 'GENERATED') {
      const error = new Error('synthetic preview result')
      error.userMessage = next.notice
      throw error
    }
  }

  const response = flow.response
  const course = response.course
  const staleCourse = flow.courseRevision !== flow.revision
  const modes = flow.profile.mobility.value ?? []
  const selectedMode = modes.length > 1 ? 'multiple' : modes[0] ?? ''

  return (
    <main className="unknown-preview">
      <h1>정보 없는 장소 포함 제안</h1>
      <p>합의 계약 기준 가상 화면 · 서버 요청과 실제 후보 검색은 수행하지 않습니다.</p>
      <label className="unknown-scenario">
        검증 시나리오
        <select value={scenario} onChange={(event) => reset(event.target.value)}>
          {Object.entries(scenarios).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>

      <section className="unknown-preview-card" aria-label="가상 여행 조건">
        <h2>여행 조건</h2>
        <label className="unknown-scenario">
          이동제약 · {flow.profile.mobility.source === 'DEFAULT' ? '기본값' : '직접 입력'} · 필수
          <select
            ref={mobilityRef}
            value={selectedMode}
            onChange={(event) => {
              const value = event.target.value
              changeMobility(value === 'multiple' ? ['WHEELCHAIR', 'STROLLER'] : value ? [value] : [])
            }}
          >
            <option value="WHEELCHAIR">휠체어</option>
            <option value="STROLLER">유모차</option>
            <option value="INJURY">부상</option>
            <option value="multiple">휠체어·유모차</option>
            <option value="">제약 없음</option>
          </select>
        </label>
        <div className="unknown-actions">
          <button type="button" onClick={() => changeMobility([...modes])}>같은 이동제약 직접 확인</button>
          {modes.length > 1 && (
            <button type="button" onClick={() => changeMobility([...modes].reverse())}>목록 순서만 변경</button>
          )}
          <button type="button" onClick={applyInfantDefault}>영유아 동반 유모차 기본값 적용</button>
        </div>
        <p>이동수단 · 도보 · {flow.profile.transport.source === 'DEFAULT' ? '기본값' : '직접 입력'}</p>
        {editingField === 'transport' && (
          <div className="unknown-actions" role="group" aria-label="가상 이동수단 편집">
            <button
              ref={transportRef}
              type="button"
              onClick={() => savePreviewProfile({
                ...flow.profile,
                transport: { ...flow.profile.transport, source: 'USER' },
              })}
            >도보로 확인하고 가상 저장</button>
            <button type="button" onClick={() => setEditingField(null)}>편집 취소</button>
          </div>
        )}
        <p>미확인 접근성 포함 · {flow.profile.includeUnknownAccessibility ? '요청함' : '요청 안 함'}</p>
        <p>가상 저장 상태 · {flow.profileStatus}</p>
        <details>
          <summary>가상 처리 기록</summary>
          <p>프로필 저장 시도 {flow.saveAttempts}회 · 현재 revision {flow.revision}</p>
          <p>코스 생성 시도 {flow.courseAttempts}회</p>
          <ol>{flow.history.map((entry, index) => <li key={index}>{entry}</li>)}</ol>
        </details>
      </section>

      <p ref={resultRef} role="status" tabIndex={-1}>{flow.notice}</p>
      {staleCourse && flow.profileStatus === 'READY' && (
        <button
          className="unknown-reset"
          type="button"
          onClick={() => setFlow(simulatePreviewCourse(flow, scenario))}
        >저장한 조건으로 코스만 다시 만들기</button>
      )}

      <section className="unknown-preview-card" aria-label="가상 코스 결과">
        <h2>{course ? '가상 코스' : '방문할 장소가 부족해요'}</h2>
        {staleCourse && <p>이전 revision의 코스예요. 이 코스의 칩은 비활성화돼요.</p>}
        {course ? (
          <>
            <p>검증 상태 · {course.validation.status}</p>
            <ol className="unknown-preview-places">
              {course.items.map((item) => (
                <li key={item.id}>
                  <strong>{item.place.name}</strong>
                  <p>접근성 등급 · {item.place.accessibility?.grade === 'VERIFIED' ? '확인됨' : '정보 없음'}</p>
                  {response.warnings.filter((warning) =>
                    warning.code === 'UNKNOWN_ACCESSIBILITY_INCLUDED'
                    && warning.placeIds?.includes(item.place.id),
                  ).map((warning) => (
                    <p key={warning.code} className="unknown-place-warning">{warning.message}</p>
                  ))}
                </li>
              ))}
            </ol>
          </>
        ) : <p>현재 조건에서 방문할 장소가 두 곳 미만이에요.</p>}

        <UnknownPlaceSuggestion
          key={scenario}
          count={response.excludedUnknown.count}
          suggestions={response.suggestions}
          disabled={staleCourse || flow.profileStatus !== 'READY' || Boolean(editingField)}
          onEditProfile={setEditingField}
          onConfirm={acceptInclusion}
        />
      </section>

      <button className="unknown-reset" type="button" onClick={() => reset(scenario)}>처음 상태로 돌아가기</button>
    </main>
  )
}
