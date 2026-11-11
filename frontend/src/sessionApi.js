export async function createSession() {
  const response = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = new Error(
      payload?.error?.message ?? '세션을 만들지 못했어요.',
    )
    error.status = response.status
    throw error
  }

  return response.json()
}

export async function saveProfile(sessionId, profile, expectedProfileRevision) {
  const response = await fetch(`/api/sessions/${sessionId}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, expectedProfileRevision }),
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = new Error(
      payload?.error?.message ?? '여행 조건을 저장하지 못했어요.',
    )

    error.status = response.status
    error.code = payload?.error?.code
    error.details = payload?.error?.details ?? []
    error.retryAfter = response.headers.get('Retry-After')
    throw error
  }

  return response.json()
}