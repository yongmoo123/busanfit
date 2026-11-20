export const includeUnknownSuggestion = {
  id: 'include-unknown-accessibility',
  type: 'INCLUDE_UNKNOWN_ACCESSIBILITY',
  label: '접근성 정보가 없는 장소도 포함해서 다시 만들까요?',
  field: 'includeUnknownAccessibility',
}

export function combinePreviewSuggestions(defaults, includeSuggestion) {
  return includeSuggestion
    ? [...defaults.slice(0, 2), includeSuggestion]
    : defaults.slice(0, 3)
}

function mobilityKey(value) {
  return JSON.stringify(value === null ? null : [...new Set(value)].sort())
}

function buildPreviewResponse(flow, scenario) {
  const response = structuredClone(flow.baseResponse)
  const hasMobility = Boolean(flow.profile.mobility.value?.length)
  const eligible = scenario !== 'none' && hasMobility
  const included = eligible && flow.profile.includeUnknownAccessibility
  const defaults = []
  for (const field of ['transport', 'mobility']) {
    if (flow.profile[field].source === 'DEFAULT') {
      defaults.push({
        id: 'edit-default-' + field,
        type: 'EDIT_PROFILE',
        field,
        label: field === 'transport'
          ? '기본 이동수단을 확인하거나 직접 선택해 주세요.'
          : '기본 이동제약을 확인하거나 직접 수정해 주세요.',
      })
    }
  }

  response.suggestions = combinePreviewSuggestions(
    defaults,
    eligible && !flow.profile.includeUnknownAccessibility ? includeUnknownSuggestion : null,
  )
  response.excludedUnknown = {
    count: eligible && !included ? 3 : 0,
    fields: eligible && !included ? [...new Set(flow.profile.mobility.value.map(
      (mode) => mode === 'STROLLER' ? 'mobility.stroller' : 'mobility.wheelchair',
    ))] : [],
  }
  response.warnings = []
  if (scenario === 'insufficient' && !included) {
    response.status = 'INSUFFICIENT_PLACES'
    response.course = null
    response.suggestions = response.suggestions.filter(
      (suggestion) => suggestion.type === 'INCLUDE_UNKNOWN_ACCESSIBILITY',
    )
    return response
  }

  response.status = 'SUCCESS'
  response.course.profileRevision = flow.revision
  for (const item of response.course.items) {
    item.place.accessibility = {
      ...item.place.accessibility,
      grade: 'VERIFIED',
      wheelchair: true,
      stroller: true,
    }
  }
  response.course.validation.status = 'PASSED'
  response.course.validation.unverifiedFields = ['price', 'routeAccessibility']
  if (included) {
    const item = structuredClone(response.course.items.at(-1))
    item.id = 'preview-unknown-item'
    item.order = response.course.items.length + 1
    item.place.id = 'preview-unknown-place'
    item.place.name = '[가상] 미확인 전시공간 C'
    item.place.accessibility = {
      ...item.place.accessibility,
      grade: 'UNKNOWN',
      wheelchair: null,
      stroller: null,
    }
    const previous = response.course.items.at(-1)
    item.startAt = new Date(new Date(previous.endAt).getTime() + 10 * 60_000).toISOString()
    item.endAt = new Date(new Date(item.startAt).getTime() + item.stayMinutes * 60_000).toISOString()
    response.course.items.push(item)
    response.course.legs.push({
      fromItemId: previous.id, toItemId: item.id, mode: 'WALK', minutes: 10,
      method: 'DISTANCE_ESTIMATE', isEstimate: true,
    })
    response.course.endAt = item.endAt
    response.course.summary.totalStayMinutes += item.stayMinutes
    response.course.summary.totalTravelMinutes += 10
    response.course.summary.totalMinutes = (
      new Date(item.endAt) - new Date(response.course.startAt)
    ) / 60_000
    response.course.validation.status = 'CONDITIONAL'
    response.course.validation.unverifiedFields.push(
      ...[...new Set(flow.profile.mobility.value.map(
        (mode) => mode === 'STROLLER' ? 'mobility.stroller' : 'mobility.wheelchair',
      ))],
    )
    response.warnings.push({
      code: 'UNKNOWN_ACCESSIBILITY_INCLUDED',
      message: '접근성 정보 없음 · 이용 가능 여부를 방문 전에 직접 확인해 주세요.',
      placeIds: [item.place.id],
    })
  }
  return response
}

export function createPreviewFlow(scenario, baseResponse, baseProfile) {
  const profile = structuredClone(baseProfile)
  profile.mobility = { value: ['WHEELCHAIR'], source: 'USER', strength: 'HARD' }
  profile.transport = { value: 'WALK', source: 'DEFAULT', strength: 'SOFT' }
  profile.includeUnknownAccessibility = false
  if (scenario === 'twoDefaults') {
    profile.companions = {
      value: { type: 'FAMILY', count: 3, hasInfant: true },
      source: 'USER',
      strength: 'SOFT',
    }
    profile.mobility = { value: ['STROLLER'], source: 'DEFAULT', strength: 'HARD' }
  }
  if (scenario === 'multiple') profile.mobility.value = ['WHEELCHAIR', 'STROLLER']

  const flow = {
    profile, baseResponse: structuredClone(baseResponse),
    revision: 1, profileStatus: 'READY', courseRevision: 1,
    saveAttempts: 0, courseAttempts: 0, history: [],
    saveFailureUsed: false, courseFailureUsed: false,
    outcome: 'INITIAL', notice: '',
  }
  flow.response = buildPreviewResponse(flow, scenario)
  return flow
}

export function simulatePreviewSave(current, requestedProfile, scenario) {
  const next = structuredClone(current)
  next.saveAttempts += 1
  next.history.push('PUT · expectedProfileRevision=' + current.revision)
  if (scenario === 'saveFailure' && !next.saveFailureUsed) {
    next.saveFailureUsed = true
    next.outcome = 'SAVE_FAILED'
    next.notice = '조건 저장에 실패했어요. 기존 조건과 코스를 유지했어요.'
    return next
  }
  const profile = structuredClone(requestedProfile)
  if (profile.companions.value?.hasInfant && profile.mobility.value === null) {
    profile.mobility = { value: ['STROLLER'], source: 'DEFAULT', strength: 'HARD' }
  }
  const changed = mobilityKey(profile.mobility.value) !== mobilityKey(current.profile.mobility.value)
  if (changed) profile.includeUnknownAccessibility = false
  next.profile = profile
  next.revision += 1
  next.profileStatus = scenario === 'needsInput' ? 'NEEDS_INPUT' : 'READY'
  next.outcome = next.profileStatus === 'READY' ? 'SAVED' : 'NEEDS_INPUT'
  next.notice = changed
    ? '이동제약이 바뀌어 포함 동의를 초기화했어요. 새 프로필 기준으로 별도 재동의가 필요해요.'
    : next.profileStatus === 'READY'
      ? '조건을 가상 저장했어요.'
      : '조건 확인이 필요해 코스를 생성하지 않았어요.'
  return next
}

export function simulatePreviewCourse(current, scenario) {
  const next = structuredClone(current)
  if (next.profileStatus !== 'READY') return next
  next.courseAttempts += 1
  next.history.push('POST · profileRevision=' + next.revision)
  if (scenario === 'failure' && !next.courseFailureUsed) {
    next.courseFailureUsed = true
    next.outcome = 'COURSE_FAILED'
    next.notice = '조건은 저장됐지만 코스 생성에 실패했어요. 코스만 다시 만들기를 눌러 주세요.'
    return next
  }
  next.courseRevision = next.revision
  next.response = buildPreviewResponse(next, scenario)
  next.outcome = 'GENERATED'
  next.notice = '가상 코스 재생성 완료 · 저장한 최신 조건을 반영했어요.'
  return next
}

export function simulatePreviewAcceptance(current, scenario) {
  let next = current
  if (!current.profile.includeUnknownAccessibility) {
    next = simulatePreviewSave(current, {
      ...current.profile, includeUnknownAccessibility: true,
    }, scenario)
    if (next.outcome !== 'SAVED') return next
  }
  return simulatePreviewCourse(next, scenario)
}
