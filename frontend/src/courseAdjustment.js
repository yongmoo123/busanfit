// FR-015: immutable response handling shared by live and mock flows.
// Requests stay sequential; a lost response must never be sent automatically again.
export function acceptAdjustmentResponse(currentCourse, requestedCourseId, revision, response) {
  if (currentCourse.id !== requestedCourseId || currentCourse.profileRevision !== revision) {
    return { course: currentCourse, ignored: true }
  }
  if (!['SUCCESS', 'NEEDS_INPUT', 'NOT_APPLIED'].includes(response.status)
      || response.profileRevision !== revision
      || response.course?.profileRevision !== revision) {
    throw new Error('수정 결과를 확인하지 못했어요. 현재 코스를 유지합니다.')
  }
  if (response.status === 'SUCCESS') {
    if (response.course.id === requestedCourseId) {
      throw new Error('새 코스를 확인하지 못했어요. 현재 코스를 유지합니다.')
    }
    return { course: response.course, ignored: false }
  }
  if (response.course.id !== requestedCourseId) {
    throw new Error('현재 코스와 다른 응답이에요. 현재 코스를 유지합니다.')
  }
  // Keep the displayed object for questions and rejected changes.
  return { course: currentCourse, ignored: false }
}

export function describeAdjustmentChanges(before, after, changes) {
  const previous = new Map(before.items.map((item) => [item.id, item]))
  const current = new Map(after.items.map((item) => [item.id, item]))
  const removed = changes.removedItemIds.map((id) => previous.get(id)).filter(Boolean)
  const replaced = changes.replacedItems.map(({ oldItemId, newItemId }) => ({
    before: previous.get(oldItemId), after: current.get(newItemId),
  })).filter((pair) => pair.before && pair.after)
  const shifted = changes.timeChangedItemIds.map((id) => ({
    before: previous.get(id), after: current.get(id),
  })).filter((pair) => pair.before && pair.after)
  return { removed, replaced, shifted }
}

export function adjustmentNeedsRecovery(error) {
  if (error.status === 429 || error.status === 400 ||
      (error.status === 422 && error.code === 'INVALID_REQUEST')) return false
  return true
}

export function adjustmentErrorMessage(error) {
  if (error.status === 429) {
    return `요청이 많아요. ${error.retryAfter ?? '잠시'}초 뒤 직접 다시 요청해 주세요. 기존 코스는 유지했어요.`
  }
  if (error.status === 400 || (error.status === 422 && error.code === 'INVALID_REQUEST')) {
    return '수정 요청 내용을 확인해 주세요. 기존 코스는 유지했어요.'
  }
  if (error.code === 'SESSION_EXPIRED' || error.status === 410) {
    return '대화가 만료됐어요. 새 대화를 시작해 주세요. 화면의 기존 코스는 그대로 두었어요.'
  }
  if (error.status === 409 || error.status === 404) {
    return '최신 코스를 확인할 수 없어요. 조건을 확인하고 새 코스를 만들어 주세요. 수정 요청은 다시 보내지 않았어요.'
  }
  if (error.status === 422) {
    return '현재는 이 수정을 사용할 수 없어요. 조건을 확인해 주세요. 기존 코스는 유지했어요.'
  }
  return '수정 결과를 받지 못했어요. 서버에서 적용됐을 수 있어 같은 요청을 다시 보내지 않았어요. 조건을 확인하고 새 코스를 만들어 주세요.'
}
