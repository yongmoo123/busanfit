import { useEffect, useId, useRef, useState } from 'react'
import { createEmptyProfile } from './profile.js'
import { stayDefaults, injuryDefaults } from './profileDefaults.js'

const areas = { HAEUNDAE: '해운대', SEOMYEON: '서면', GWANGALLI: '광안리', NAMPO: '남포' }
const transports = { WALK: '도보', PUBLIC: '대중교통', CAR: '자차' }
const mobilityOptions = { WHEELCHAIR: '휠체어', STROLLER: '유모차', INJURY: '부상' }
const preferences = { INDOOR: '실내', OUTDOOR: '실외', ANY: '상관없음' }
const companionTypes = { SOLO: '혼자', FRIENDS: '친구', COUPLE: '연인', FAMILY: '가족', OTHER: '기타' }
const categories = {
  CAFE: '카페', FOOD: '음식점', EXHIBITION: '전시', ATTRACTION: '관광지',
  PARK: '공원', SHOPPING: '쇼핑', OTHER: '기타',
}
const budgetItems = { ADMISSION: '입장료', FOOD: '식비', TRANSPORT: '교통비' }
const budgetBases = { PER_PERSON: '1인 기준', TOTAL: '전체 기준' }
const fields = {
  area: '여행 지역', timeWindow: '이용 시간', transport: '이동수단',
  mobility: '이동제약', budget: '예산', indoorPreference: '실내·실외 선호',
  companions: '동행', excludedCategories: '제외 카테고리', preferenceTags: '선호 태그',
  includeUnknownAccessibility: '접근성 미확인 장소 포함',
}
const sources = { USER: '직접 입력', DEFAULT: '기본값', UNSET: '미입력' }

function Choice({ label, options, value, onChange, placeholder = '미입력', required = false, inputRef }) {
  return (
    <label className="profile-control">
      <span>{label}</span>
      <select ref={inputRef} className="condition-select" value={value ?? ''} required={required}
        onChange={(event) => onChange(event.target.value || null)}>
        <option value="">{placeholder}</option>
        {Object.entries(options).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
      </select>
    </label>
  )
}

function Checks({ options, selected, onChange }) {
  return (
    <div className="profile-checks">
      {Object.entries(options).map(([value, label]) => (
        <label key={value}>
          <input type="checkbox" checked={selected.includes(value)}
            onChange={(event) => onChange(event.target.checked
              ? [...selected, value]
              : selected.filter((item) => item !== value))} />
          {label}
        </label>
      ))}
    </div>
  )
}

function ListInput({ value, options, onChange, emptyLabel }) {
  return (
    <>
      <p>{value === null ? '미입력' : value.length === 0 ? emptyLabel : value.map((item) => options[item]).join(', ')}</p>
      <Checks options={options} selected={value ?? []} onChange={onChange} />
      <div className="profile-actions">
        <button type="button" className="profile-secondary" onClick={() => onChange(null)}>미입력으로 지우기</button>
        <button type="button" className="profile-secondary" onClick={() => onChange([])}>{emptyLabel}</button>
      </div>
    </>
  )
}

function seoulInput(value) {
  if (!value) return ''
  const shifted = new Date(new Date(value).getTime() + 9 * 60 * 60 * 1000)
  return shifted.toISOString().slice(0, 16)
}

function TimeFields({ value, onChange }) {
  if (value === null) {
    return <button type="button" className="profile-secondary"
      onClick={() => onChange({ startAt: '', endAt: '' })}>이용 시간 입력</button>
  }

  function change(name, input) {
    onChange({ ...value, [name]: input ? input + ':00+09:00' : '' })
  }

  return (
    <>
      <p>한국 시간 기준</p>
      <label className="profile-control">
        <span>시작 시간</span>
        <input type="datetime-local" required value={seoulInput(value.startAt)}
          onChange={(event) => change('startAt', event.target.value)} />
      </label>
      <label className="profile-control">
        <span>종료 시간</span>
        <input type="datetime-local" required value={seoulInput(value.endAt)}
          onChange={(event) => change('endAt', event.target.value)} />
      </label>
      <button type="button" className="profile-secondary" onClick={() => onChange(null)}>이용 시간 지우기</button>
    </>
  )
}

function BudgetFields({ value, onChange }) {
  if (value === null) {
    return <><p>제한 없음 (기본값). 금액을 입력하지 않았으며, 무료라는 뜻은 아니에요.</p>
      <button type="button" className="profile-secondary"
        onClick={() => onChange({ amount: null, currency: 'KRW', basis: null, includes: [] })}>예산 입력</button></>
  }

  return (
    <>
      <label className="profile-control">
        <span>금액 (원)</span>
        <input type="number" min="0" step="1" required value={value.amount ?? ''}
          onChange={(event) => onChange({
            ...value, amount: event.target.value === '' ? null : event.target.valueAsNumber,
          })} />
      </label>
      <Choice label="금액 기준" options={budgetBases} value={value.basis} required
        onChange={(basis) => onChange({ ...value, basis })} />
      <p>예산에 포함할 항목</p>
      <Checks options={budgetItems} selected={value.includes}
        onChange={(includes) => onChange({ ...value, includes })} />
      <button type="button" className="profile-secondary" onClick={() => onChange(null)}>예산 지우기</button>
    </>
  )
}

function CompanionFields({ value, onChange }) {
  if (value === null) {
    return <button type="button" className="profile-secondary"
      onClick={() => onChange({ type: null, count: null, hasInfant: null })}>동행 입력</button>
  }

  return (
    <>
      <Choice label="동행 유형" options={companionTypes} value={value.type} required
        onChange={(type) => onChange({ ...value, type })} />
      <label className="profile-control">
        <span>인원</span>
        <input type="number" min="1" step="1" required value={value.count ?? ''}
          onChange={(event) => onChange({
            ...value, count: event.target.value === '' ? null : event.target.valueAsNumber,
          })} />
      </label>
      <Choice label="영유아 동반" options={{ yes: '동반', no: '동반하지 않음' }} required
        value={value.hasInfant === null ? null : value.hasInfant ? 'yes' : 'no'}
        onChange={(answer) => onChange({ ...value, hasInfant: answer === null ? null : answer === 'yes' })} />
      <button type="button" className="profile-secondary" onClick={() => onChange(null)}>동행 정보 지우기</button>
    </>
  )
}

function ProfileField({ name, condition, error, onStrength, children }) {
  const titleId = useId()
  const errorId = useId()

  return (
    <div className="condition-item profile-field" role="group" data-profile-field={name}
      aria-labelledby={titleId} aria-describedby={error ? errorId : undefined} aria-invalid={Boolean(error)}>
      <h4 id={titleId} className="profile-field-title">{fields[name]}</h4>
      {children}
      {condition && (
        <div className="profile-meta">
          <span className={condition.source === 'DEFAULT' ? 'profile-default' : undefined}>
            {name === 'budget' && condition.value === null ? '제한 없음 (기본값)' : sources[condition.source]}
          </span>
          {name === 'area' || name === 'timeWindow' || name === 'mobility' || condition.value === null || condition.source === 'DEFAULT'
            ? <span>{condition.strength === 'HARD' ? '필수' : '선호'}</span>
            : <label>
                강도
                <select value={condition.strength} onChange={(event) => onStrength(event.target.value)}>
                  <option value="HARD">필수</option>
                  <option value="SOFT">선호</option>
                </select>
              </label>}
        </div>
      )}
      {error && <p id={errorId} className="profile-error" role="alert">{error}</p>}
    </div>
  )
}

function saveError(error) {
  const prefix = error.status ? error.status + ' · ' : ''
  switch (error.status) {
    case 409:
      return { message: prefix + '조건이 다른 요청에서 변경됐어요. 최신 조건을 불러올 수 없어 새 세션에서 다시 입력해 주세요.', restart: true }
    case 410:
      return { message: prefix + '세션이 만료됐어요. 새 세션에서 다시 입력해 주세요.', restart: true }
    case 422:
      return { message: prefix + error.message, details: error.details }
    case 429:
      return { message: prefix + (error.retryAfter
        ? error.retryAfter + '초 뒤 다시 저장해 주세요.'
        : '요청이 많아요. 잠시 뒤 다시 저장해 주세요.') }
    case 503:
      return { message: prefix + '자동 조건 처리를 사용할 수 없어요. 조건을 직접 입력해 주세요.', directInput: true }
    default:
      return { message: error.status ? prefix + error.message : '서버에 연결하지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.' }
  }
}

export default function ProfileEditor({ initialProfile, isMock, canSave, sessionError, capabilities, onSave, onRestart, onClose }) {
  const titleId = useId()
  const [profile, setProfile] = useState(() => structuredClone(initialProfile))
  const [tags, setTags] = useState(() => initialProfile.preferenceTags.value?.join(', ') ?? '')
  const [feedback, setFeedback] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const savingRef = useRef(false)
  const areaInputRef = useRef(null)
  const formRef = useRef(null)

  useEffect(() => {
    const first = feedback?.details?.[0]?.field?.split('.')[0]
    if (!first) return
    const group = [...(formRef.current?.querySelectorAll('[data-profile-field]') ?? [])]
      .find((element) => element.dataset.profileField === first)
    group?.querySelector('select, input, button')?.focus()
  }, [feedback])

  function edit(name, value, strength) {
    setProfile((current) => ({
      ...current,
      [name]: name === 'includeUnknownAccessibility' ? value : {
        value,
        source: value === null ? 'UNSET' : 'USER',
        strength: strength ?? current[name].strength,
      },
    }))
    setDirty(true)
    setFeedback((current) => current?.restart ? current : null)
  }

  function detailFor(name) {
    return feedback?.details?.find((detail) => detail.field === name || detail.field.startsWith(name + '.'))?.reason
  }

  function field(name, children) {
    const condition = name === 'includeUnknownAccessibility' ? null : profile[name]
    return (
      <ProfileField name={name} condition={condition} error={detailFor(name)}
        onStrength={(strength) => edit(name, condition.value, strength)}>
        {children}
        {capabilities && (name === 'includeUnknownAccessibility'
          ? !capabilities.supportsUnknownAccessibilityInclusion
          : !capabilities.supportedProfileFields.includes(name)) &&
          <p className="profile-support-note">현재 지원하지 않는 조건이에요. 미입력·제약 없음·포함 안 함 상태는 유지할 수 있어요.</p>}
      </ProfileField>
    )
  }

  async function submit(event) {
    event.preventDefault()
    if (!canSave || !dirty || savingRef.current || feedback?.restart) return

    if (profile.budget.value && profile.budget.value.includes.length === 0) {
      setFeedback({ error: true, details: [{ field: 'budget', reason: '예산에 포함할 항목을 하나 이상 선택해 주세요.' }] })
      return
    }

    savingRef.current = true
    setIsSaving(true)
    setFeedback(null)
    try {
      const result = await onSave(profile)
      setProfile(result.profile)
      setTags(result.profile.preferenceTags.value?.join(', ') ?? '')
      setDirty(false)
      setFeedback({ message: isMock ? '가상 응답 · 여행 조건을 저장했어요.' : '여행 조건을 저장했어요.', result })
    } catch (error) {
      setFeedback({ ...saveError(error), error: true })
    } finally {
      setIsSaving(false)
      savingRef.current = false
    }
  }

  function restart() {
    setProfile(createEmptyProfile())
    setTags('')
    setDirty(false)
    setFeedback(null)
    onRestart()
  }

  return (
    <section className="condition-card profile-editor" aria-labelledby={titleId}>
      <div className="condition-card-heading">
        <div>
          <h3 id={titleId}>내 여행 조건</h3>
          <p>{isMock ? '가상 조건과 응답으로 저장을 시연합니다.' : '직접 입력한 조건을 서버에 저장합니다.'}</p>
        </div>
        <span className="ready-badge">{isMock ? '가상 저장 시연' : '실제 API'}</span>
      </div>
      {capabilities && <p className="profile-support-note" role="status">
        {capabilities.supportedAreas.length ? `지원 지역: ${capabilities.supportedAreas.map((area) => areas[area]).join(', ')} · 이동수단: ${capabilities.supportedTransports.map((mode) => transports[mode]).join(', ')}`
          : '현재 일반 서비스의 조건 저장은 준비 중이에요.'}
      </p>}
      <details className="profile-default-guide">
        <summary>기본 체류시간과 적용 기준</summary>
        <p>시설의 관람소요시간이 있으면 먼저 사용하고, 없으면 아래 기본값을 사용해요. 코스 계산에 쓰는 기준이며 장소의 실제 운영시간을 뜻하지 않아요.</p>
        <ul>{Object.entries(stayDefaults).map(([category, minutes]) => <li key={category}>{categories[category]}: {minutes}분</li>)}</ul>
      </details>
      <form ref={formRef} onSubmit={submit}>
        <fieldset className="profile-form-fields" disabled={isSaving}>
          <div className="condition-grid">
            {field('area', <Choice label="지역 선택" inputRef={areaInputRef} options={areas} value={profile.area.value}
              onChange={(value) => edit('area', value)} />)}
            {field('transport', <>
              <Choice label="이동수단 선택" options={transports} value={profile.transport.value}
                onChange={(value) => edit('transport', value)} />
              {capabilities?.supportedTransports.includes('WALK') && <button type="button" className="profile-secondary"
                onClick={() => edit('transport', null)}>도보 기본값으로 초기화</button>}
              <p>미지원 이동수단 확인 중에는 초기화나 다른 항목 저장으로 수락 처리하지 않아요.</p>
            </>)}
            {field('timeWindow', <TimeFields value={profile.timeWindow.value}
              onChange={(value) => edit('timeWindow', value)} />)}
            {field('mobility', <>
              <ListInput value={profile.mobility.value} options={mobilityOptions}
                emptyLabel="제약 없음" onChange={(value) => edit('mobility', value, 'HARD')} />
              <p>미입력으로 지우면 영유아 동반 시 유모차 기본값 적용 대상으로 돌아가요. 제약 없음을 고르면 자동 적용하지 않아요.</p>
              {profile.mobility.value?.includes('INJURY') && <div className="profile-injury-note" role="note">
                <strong>부상 조건 처리 기준</strong>
                <p>보행 속도는 일반 {injuryDefaults.normalWalkingKmh}km/h 대신 {injuryDefaults.walkingKmh}km/h, 구간당 최대 도보는 {injuryDefaults.maxLegWalkingMinutes}분을 초기 설정으로 사용해요.</p>
                <p>계단 회피는 장소의 휠체어 접근 가능 정보로 보수적으로 판정해요. 실제 이동 경로의 계단·경사는 확인되지 않아요. 후보가 부족해도 조건을 자동 해제하지 않아요.</p>
                {!capabilities?.supportedProfileFields.includes('mobility') && <p>이동제약 지원이 준비 중이라 현재 선택한 조건을 저장할 수 없어요.</p>}
              </div>}
            </>)}
            {field('budget', <BudgetFields value={profile.budget.value} onChange={(value) => edit('budget', value)} />)}
            {field('companions', <CompanionFields value={profile.companions.value}
              onChange={(value) => edit('companions', value)} />)}
            {field('indoorPreference', <Choice label="장소 선호 선택" options={preferences}
              value={profile.indoorPreference.value} onChange={(value) => edit('indoorPreference', value)} />)}
            {field('excludedCategories', <ListInput value={profile.excludedCategories.value} options={categories}
              emptyLabel="제외 없음" onChange={(value) => edit('excludedCategories', value)} />)}
            {field('preferenceTags', <>
              <label className="profile-control">
                <span>쉼표로 구분</span>
                <input value={tags} onChange={(event) => {
                  const text = event.target.value
                  setTags(text)
                  edit('preferenceTags', [...new Set(text.split(',').map((tag) => tag.trim()).filter(Boolean))])
                }} />
              </label>
              <button type="button" className="profile-secondary" onClick={() => {
                setTags('')
                edit('preferenceTags', null)
              }}>미입력으로 지우기</button>
            </>)}
            {field('includeUnknownAccessibility', <label className="profile-checks">
              <input type="checkbox" checked={profile.includeUnknownAccessibility}
                onChange={(event) => edit('includeUnknownAccessibility', event.target.checked)} />
              포함 요청
            </label>)}
          </div>
        </fieldset>

        {!isMock && !canSave && (
          sessionError ? (
            <div className="profile-actions">
              <p className="profile-error" role="alert">{sessionError}</p>
              <button type="button" className="profile-secondary" onClick={onRestart}>다시 연결</button>
            </div>
          ) : <p role="status">저장 서버에 연결 중이에요.</p>
        )}
        {feedback?.message && <p className={feedback.error ? 'profile-error' : undefined}
          role={feedback.error ? 'alert' : 'status'}>{feedback.message}</p>}
        {feedback?.directInput && (
          <button type="button" className="profile-secondary"
          onClick={() => areaInputRef.current?.focus()}>조건 직접 입력</button>
        )}
        {feedback?.details?.filter((detail) => !Object.keys(fields).some(
          (name) => detail.field === name || detail.field.startsWith(name + '.'),
        )).map((detail, index) => <p className="profile-error" role="alert" key={index}>{detail.reason}</p>)}
        {feedback?.result && (
          <div className="profile-response-notes">
            <p>{feedback.result.status === 'READY' ? '조건 확인 완료' : '추가 조건 입력 필요'}</p>
            {[...(feedback.result.questions ?? []), ...(feedback.result.warnings ?? [])]
              .map((item, index) => <p key={index}>{item.message}</p>)}
          </div>
        )}

        <div className="profile-actions">
          {feedback?.restart
            ? <button type="button" className="primary-button" onClick={restart}>새 세션 시작</button>
            : <button className="primary-button" type="submit" disabled={!canSave || !dirty || isSaving}>
                {isSaving ? '저장 중…' : isMock ? '가상으로 저장' : '조건 저장 (실제 API)'}
              </button>}
          <button type="button" className="profile-secondary" onClick={onClose} disabled={isSaving}>닫기</button>
        </div>
      </form>
    </section>
  )
}
