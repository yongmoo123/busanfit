export function buildInclusionProfile(session) {
  if (session?.capabilities?.supportsUnknownAccessibilityInclusion !== true) {
    throw new Error('현재 서버는 정보 없는 장소 포함을 지원하지 않아요. 새 대화에서 지원 여부를 확인해 주세요.')
  }
  if (!session.savedProfile || session.profileStatus !== 'READY') {
    throw new Error('최신 여행 조건을 먼저 저장하고 확인해 주세요.')
  }
  return { ...structuredClone(session.savedProfile), includeUnknownAccessibility: true }
}

export function selectCourseSuggestions(suggestions = [], inclusionSupported = false) {
  const defaults = suggestions.filter((item) => item.type === 'EDIT_PROFILE')
  const include = inclusionSupported && suggestions.find((item) => item.type === 'INCLUDE_UNKNOWN_ACCESSIBILITY')
  return include ? [...defaults.slice(0, 2), include] : defaults.slice(0, 3)
}

export function includedUnknownPlaceIds(warnings = []) {
  return new Set(warnings.filter((item) => item.code === 'UNKNOWN_ACCESSIBILITY_INCLUDED')
    .flatMap((item) => item.placeIds ?? []))
}
