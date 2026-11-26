async function requestJson(url, options, fallbackMessage) {
  const response = await fetch(url, options)

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = new Error(payload?.error?.message ?? fallbackMessage)
    error.status = response.status
    error.code = payload?.error?.code
    error.retryAfter = response.headers.get('Retry-After')
    throw error
  }

  return response.json()
}

export function createCourse(sessionId, profileRevision, signal) {
  return requestJson(
    '/api/courses',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, profileRevision }),
      signal,
    },
    '코스를 만들지 못했어요.',
  )
}

export function getPlaceDetail(placeId, signal) {
  return requestJson(
    `/api/places/${encodeURIComponent(placeId)}`,
    { signal },
    '장소 상세 정보를 불러오지 못했어요.',
  )
}
export function adjustCourse(sessionId, courseId, expectedProfileRevision, message, signal) {
  return requestJson(
    `/api/courses/${encodeURIComponent(courseId)}/adjust`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, expectedProfileRevision, message }),
      signal,
    },
    '코스를 수정하지 못했어요.',
  )
}
