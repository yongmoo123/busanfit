import baseResponse from './mocks/07-adjust.base.response.json'

export const adjustmentScenarios = [
  ['remove', '장소 빼기 성공', '2번 빼줘'],
  ['replace', '같은 시간대 장소 교체 성공', '2번 다른 카페로 바꿔줘'],
  ['replace-unavailable', '교체 후보 없음·이유와 대안 안내', '2번 다른 카페로 바꿔줘'],
  ['extend', '체류 늘리기·뒤 장소 시각 변경', '2번에 30분 더 머물래'],
  ['question', '연장 시간 추가 질문', '2번에 더 머물래'],
  ['rejected', '수정 불가·기존 코스 유지', '2번에 180분 더 머물래'],
  ['followup', '첫 수정 성공·나머지 확인 질문', '2번 빼고 3번에 30분 더 머물래'],
  ['conflict', '409 최신 코스 충돌', '2번 빼줘'],
  ['network', '응답 유실·자동 재전송 안 함', '2번 빼줘'],
]

const blankChanges = () => ({ removedItemIds: [], replacedItems: [], timeChangedItemIds: [] })
const minute = 60 * 1000
function plusMinutes(date, count) {
  // The fixture is KST. Preserve the offset representation for readable changes.
  return new Date(new Date(date).getTime() + count * minute + 9 * 60 * minute)
    .toISOString().slice(0, 19) + '+09:00'
}

export function initialPreviewCourse() {
  const course = structuredClone(baseResponse.course)
  course.availableWindow.endAt = '2026-11-06T18:00:00+09:00'
  const third = structuredClone(course.items[0])
  third.id = 'item-03'
  third.order = 3
  third.place.id = 'mock-place-003'
  third.place.name = '[가상] 전시공간 C'
  third.startAt = '2026-11-06T15:20:00+09:00'
  third.endAt = '2026-11-06T16:20:00+09:00'
  course.items.push(third)
  course.legs.push({ ...course.legs[0], fromItemId: 'item-02', toItemId: 'item-03' })
  return refreshSummary(course)
}

function refreshSummary(course) {
  course.startAt = course.items[0].startAt
  course.endAt = course.items.at(-1).endAt
  const totalStayMinutes = course.items.reduce((total, item) => total + item.stayMinutes, 0)
  const totalTravelMinutes = course.legs.reduce((total, leg) => total + leg.minutes, 0)
  const totalMinutes = (new Date(course.endAt) - new Date(course.startAt)) / minute
  course.summary = { ...course.summary, totalStayMinutes, totalTravelMinutes, totalMinutes,
    totalWaitingMinutes: totalMinutes - totalStayMinutes - totalTravelMinutes }
  return course
}

// Scenario selection controls mock outcomes, not natural-language understanding.
// No fetch, model call, session ID or real location is used here.
export function simulateAdjustment(scenario, original, sequence = 1, answer = '') {
  if (scenario === 'network') throw new Error('Mock response loss')
  if (scenario === 'conflict') {
    throw Object.assign(new Error('Mock conflict'), { status: 409, code: 'COURSE_CONFLICT' })
  }
  const response = { ...structuredClone(baseResponse), course: structuredClone(original),
    profileRevision: original.profileRevision, changes: blankChanges(), questions: [], status: 'SUCCESS' }
  let operation = scenario
  if (scenario === 'followup' && !original.items.some((item) => item.id === 'item-02')) {
    if (!/^(네|예|응|좋아요|늘려줘)$/.test(answer.trim())) {
      return { ...response, status: 'NEEDS_INPUT', questions: [
        { field: 'adjustment.followUp', message: '전시공간 C(현재 2번)에 30분 더 머물까요? 가상 화면에서는 네라고 답해 주세요.' },
      ] }
    }
    operation = 'extend-last'
  }
  if (scenario === 'question') {
    if (!/^(30|30분|30분 더)$/.test(answer.trim())) {
      return { ...response, status: 'NEEDS_INPUT', questions: [
        { field: 'adjustment.minutes', message: '몇 분 더 머무를까요? (가상 화면에서는 30분으로 답해 주세요.)' },
      ] }
    }
    operation = 'extend'
  }
  if (scenario === 'replace-unavailable') {
    response.status = 'NOT_APPLIED'
    response.warnings.push({ code: 'ADJUSTMENT_NOT_FEASIBLE',
      message: '[가상] 원래 방문 시간대에 영업하고 앞뒤 이동시간까지 맞는 교체 후보가 없어요. 기존 코스를 유지했어요. 대안으로 해당 장소 빼기나 체류 늘리기를 요청할 수 있어요. 다른 수정도 조건을 만족할 때만 적용돼요.',
      placeIds: [] })
    return response
  }
  if (scenario === 'rejected') {
    response.status = 'NOT_APPLIED'
    response.warnings.push({ code: 'ADJUSTMENT_NOT_FEASIBLE',
      message: '[가상] 이용 시간이나 영업시간을 넘어서 변경할 수 없어요. 연장 시간을 줄여 다시 요청해 주세요.', placeIds: [] })
    return response
  }
  const course = response.course
  const second = course.items.find((item) => item.id === 'item-02')
  if (operation === 'remove' || operation === 'followup') {
    if (!second || course.items.length <= 2) {
      return { ...response, status: 'NOT_APPLIED', warnings: [...response.warnings,
        { code: 'ADJUSTMENT_NOT_FEASIBLE', message: '[가상] 두 곳 이상을 유지해야 해서 더 뺄 수 없어요.', placeIds: [] }] }
    }
    course.items = course.items.filter((item) => item.id !== second.id)
    course.legs = [{ ...course.legs[0], fromItemId: 'item-01', toItemId: 'item-03' }]
    response.changes.removedItemIds = [second.id]
    if (operation === 'followup') response.questions = [
      { field: 'adjustment.followUp', message: '2번을 뺐어요. 원래 3번이었던 전시공간 C(현재 2번)에 30분 더 머무를까요?' },
    ]
  } else if (operation === 'replace' && second) {
    const oldId = second.id
    second.id = `item-replaced-${sequence}`
    second.place.id = 'mock-place-004'
    second.place.name = '[가상] 다른 카페 D'
    course.legs = course.legs.map((leg) => ({ ...leg,
      fromItemId: leg.fromItemId === oldId ? second.id : leg.fromItemId,
      toItemId: leg.toItemId === oldId ? second.id : leg.toItemId }))
    response.changes.replacedItems = [{ oldItemId: oldId, newItemId: second.id }]
  } else if (operation === 'extend' && second) {
    second.endAt = plusMinutes(second.endAt, 30)
    second.stayMinutes += 30
    response.changes.timeChangedItemIds = [second.id]
    const third = course.items.find((item) => item.id === 'item-03')
    if (third) {
      third.startAt = plusMinutes(third.startAt, 30)
      third.endAt = plusMinutes(third.endAt, 30)
      response.changes.timeChangedItemIds.push(third.id)
    }
  } else if (operation === 'extend-last') {
    const last = course.items.at(-1)
    last.endAt = plusMinutes(last.endAt, 30)
    last.stayMinutes += 30
    response.changes.timeChangedItemIds = [last.id]
  } else {
    return { ...response, status: 'NEEDS_INPUT', questions: [
      { field: 'adjustment.message', message: '처음 상태로 돌아간 뒤 다른 검증 시나리오를 선택해 주세요.' },
    ] }
  }
  course.id = `44444444-4444-4444-8444-${String(sequence).padStart(12, '0')}`
  course.items.forEach((item, index) => { item.order = index + 1 })
  refreshSummary(course)
  if (new Date(course.endAt) > new Date(course.availableWindow.endAt)) {
    return { ...response, status: 'NOT_APPLIED', course: structuredClone(original), changes: blankChanges(),
      questions: [], warnings: [...response.warnings, { code: 'ADJUSTMENT_NOT_FEASIBLE',
        message: '[가상] 이용 시간을 넘어서 연장할 수 없어요. 연장 시간을 줄여 주세요.', placeIds: [] }] }
  }
  return response
}
