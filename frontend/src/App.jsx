
import { useEffect, useRef, useState } from 'react'
import readyMock from './mocks/02-chat.ready.response.json'
import { createSession, saveProfile, sendChat, deleteSession } from './sessionApi.js'
import { createEmptyProfile } from './profile.js'
import { budgetLabel } from './profileDefaults.js'
import ProfileEditor from './ProfileEditor.jsx'
import CourseTimeline from './CourseTimeline.jsx'
import { createCourse, adjustCourse } from './courseApi.js'
import CourseAdjustmentPanel from './CourseAdjustmentPanel.jsx'
import CourseAdjustmentResult from './CourseAdjustmentResult.jsx'
import { acceptAdjustmentResponse, adjustmentErrorMessage, adjustmentNeedsRecovery } from './courseAdjustment.js'
import { buildInclusionProfile } from './unknownInclusion.js'
import './App.css'

const MIN_SIDEBAR_WIDTH = 220
const MAX_SIDEBAR_WIDTH = 480
const DEFAULT_SIDEBAR_WIDTH = 270

const exampleHistory = [
  '해운대 여행 계획',
  '광안리에서 보내는 하루',
  '서면 친구들과 놀거리',
]

function getInitialSidebarWidth() {
  try {
    const saved = Number(localStorage.getItem('busanfit-sidebar-width'))
    if (saved >= MIN_SIDEBAR_WIDTH && saved <= MAX_SIDEBAR_WIDTH) {
      return saved
    }
  } catch {
    // 브라우저 저장소를 사용할 수 없는 경우 기본값 사용
  }

  return DEFAULT_SIDEBAR_WIDTH
}

function formatDateTime(value) {
  if (!value) return '미입력'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString('ko-KR', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  })
}

function getAreaName(value) {
  const names = {
    HAEUNDAE: '해운대',
    SEOMYEON: '서면',
    GWANGALLI: '광안리',
    NAMPO: '남포',
  }
  return names[value] ?? value ?? '미입력'
}

function getTransportName(value) {
  const names = {
    WALK: '도보',
    PUBLIC: '대중교통',
    CAR: '자차',
  }
  return names[value] ?? value ?? '미입력'
}

function getCompanionsName(value) {
  if (!value) return '미입력'

  const names = {
    SOLO: '혼자',
    ALONE: '혼자',
    FRIENDS: '친구',
    FAMILY: '가족',
    COUPLE: '연인',
  }

  const type = names[value.type] ?? value.type ?? '동행'
  return value.count ? `${type} · ${value.count}명` : type
}

function ConditionCard({ profile, onRecommend, onEdit, ready, disabled = false }) {
  const timeWindow = profile?.timeWindow?.value

  const items = [
    { field: 'area', label: '여행 지역', value: getAreaName(profile?.area?.value) },
    { field: 'transport', label: '이동수단', value: getTransportName(profile?.transport?.value) },
    { field: 'timeWindow', label: '시작 시간', value: formatDateTime(timeWindow?.startAt) },
    { field: 'timeWindow', label: '종료 시간', value: formatDateTime(timeWindow?.endAt) },
    { field: 'companions', label: '동행 인원', value: getCompanionsName(profile?.companions?.value) },
    { field: 'budget', label: '예산', value: budgetLabel(profile.budget) },
    { field: 'mobility', label: '이동제약', value: profile?.mobility?.value?.map((value) => ({ WHEELCHAIR: '휠체어', STROLLER: '유모차', INJURY: '부상' })[value]).join(', ') || (profile?.mobility?.value === null ? '미입력' : '제약 없음') },
    { field: 'indoorPreference', label: '장소 선호', value: ({ INDOOR: '실내', OUTDOOR: '실외', ANY: '상관없음' })[profile?.indoorPreference?.value] ?? '미입력' },
    { field: 'excludedCategories', label: '제외 카테고리', value: profile?.excludedCategories?.value?.map((value) => ({ CAFE: '카페', FOOD: '음식점', EXHIBITION: '전시', ATTRACTION: '관광지', PARK: '공원', SHOPPING: '쇼핑', OTHER: '기타' })[value]).join(', ') || (profile?.excludedCategories?.value === null ? '미입력' : '제외 없음') },
  ]

  return (
    <div className="condition-card">
      <div className="condition-card-heading">
        <div>
          <h3>내 여행 조건</h3>
        </div>
      </div>

      <div className="condition-grid">
        {items.map((item) => (
          <div className="condition-item" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {(profile?.[item.field]?.source === 'DEFAULT' || (item.field === 'budget' && profile.budget.value === null)) && <span className="profile-default">기본값</span>}
            {profile?.[item.field]?.value !== null && <span className="condition-strength">{profile?.[item.field]?.strength === 'HARD' ? '필수' : '선호'}</span>}
          </div>
        ))}
      </div>

      <p>접근성 미확인 장소 포함: {profile.includeUnknownAccessibility ? '요청함' : '요청 안 함'}</p>
      <div className="profile-actions">
        <button type="button" className="primary-button" disabled={disabled} onClick={onEdit}>조건 편집</button>
        <button type="button" className="profile-secondary" disabled={!ready || disabled} onClick={onRecommend}>코스 만들기</button>
      </div>
    </div>
  )
}

function Sidebar({
  isOpen,
  onClose,
  onNewChat,
  width,
  onResizeStart,
}) {
  return (
    <>
      {isOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="사이드바 닫기"
          onClick={onClose}
        />
      )}

      <aside
        className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}
        style={{ width: `${width}px` }}
      >
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <span className="brand-symbol">✦</span>
            <strong>BusanFit</strong>
          </div>
          <button
            type="button"
            className="icon-button sidebar-close"
            aria-label="사이드바 닫기"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <button
          className="new-chat-button"
          type="button"
          onClick={onNewChat}
        >
          <span>＋</span>
          새 채팅
        </button>

        <div className="sidebar-section">
          <span className="sidebar-section-title">최근 여행 계획</span>

          {exampleHistory.map((title) => (
            <div className="history-item" key={title}>
              <span className="history-icon">◷</span>
              <span>{title}</span>
            </div>
          ))}

          <p className="sidebar-hint">
            위 목록은 디자인 확인용 예시입니다.
          </p>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-avatar">B</div>
          <div>
            <strong>BusanFit 여행 플래너</strong>
            <span>부산에서 나만의 하루를</span>
          </div>
        </div>

        <div
          className="sidebar-resizer"
          role="separator"
          aria-label="사이드바 너비 조절"
          aria-orientation="vertical"
          aria-valuemin={MIN_SIDEBAR_WIDTH}
          aria-valuemax={MAX_SIDEBAR_WIDTH}
          aria-valuenow={width}
          tabIndex={0}
          onPointerDown={onResizeStart}
        />
      </aside>
    </>
  )
}

function App() {
  const [editor, setEditor] = useState(() => {
    const isProfileQa = import.meta.env.DEV &&
      new URLSearchParams(window.location.search).get('qa') === 'profile-save'
    return isProfileQa ? { target: 'qa', isMock: true } : null
  })
  const isQaEditor = editor?.target === 'qa'
  const [session, setSession] = useState(null)
  const [sessionError, setSessionError] = useState('')
  const [sessionAttempt, setSessionAttempt] = useState(0)
  const sessionRequestRef = useRef(null)
  const profileSaveRef = useRef(false)
  const courseRequestRef = useRef(null)
  const [isCreatingCourse, setIsCreatingCourse] = useState(false)
  const [isIncludingUnknown, setIsIncludingUnknown] = useState(false)
  const [courseRetry, setCourseRetry] = useState(null)
  const unknownRequestRef = useRef(false)
  const adjustmentRequestRef = useRef(null)
  const latestCourseRef = useRef(null)
  const [isAdjustingCourse, setIsAdjustingCourse] = useState(false)

  useEffect(() => {
    if (isQaEditor) return undefined

    let active = true

    if (sessionRequestRef.current === null) {
      sessionRequestRef.current = createSession()
    }

    sessionRequestRef.current
      .then((created) => {
        if (active) {
          setSession({ ...created, profileRevision: 0 })
        }
      })
      .catch((error) => {
        if (active) {
          setSessionError(
            error.status ? error.message : '서버에 연결하지 못했어요.',
          )
        }
      })

    return () => {
      active = false
    }
  }, [isQaEditor, sessionAttempt])

  function retrySession() {
    if (profileSaveRef.current || unknownRequestRef.current) return
    courseRequestRef.current?.abort()
    adjustmentRequestRef.current?.abort()
    adjustmentRequestRef.current = null
    latestCourseRef.current = null
    setIsAdjustingCourse(false)
    setCourseRetry(null)
    if (session?.sessionId) deleteSession(session.sessionId).catch(() => {})
    sessionRequestRef.current = null
    setSession(null)
    setSessionError('')
    setMessages([])
    setEditor(null)
    setSessionAttempt((current) => current + 1)
  }

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(getInitialSidebarWidth)
  const [isResizing, setIsResizing] = useState(false)

  const messagesEndRef = useRef(null)
  const chatAbortRef = useRef(null)
  const resizingRef = useRef(false)

  const hasMessages = messages.length > 0

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end',
    })
  }, [messages, isSending])

  useEffect(() => {
    return () => {
      chatAbortRef.current?.abort()
      courseRequestRef.current?.abort()
      adjustmentRequestRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!isResizing) return undefined

    function handlePointerMove(event) {
      if (!resizingRef.current) return

      const maxWidth = Math.min(
        MAX_SIDEBAR_WIDTH,
        window.innerWidth - 320,
      )

      const nextWidth = Math.max(
        MIN_SIDEBAR_WIDTH,
        Math.min(event.clientX, maxWidth),
      )

      setSidebarWidth(nextWidth)
    }

    function stopResizing() {
      resizingRef.current = false
      setIsResizing(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResizing)
    window.addEventListener('pointercancel', stopResizing)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResizing)
      window.removeEventListener('pointercancel', stopResizing)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

  useEffect(() => {
    try {
      localStorage.setItem('busanfit-sidebar-width', String(sidebarWidth))
    } catch {
      // 저장소 사용 불가 시 현재 화면에서만 너비 유지
    }
  }, [sidebarWidth])

  function handleResizeStart(event) {
    if (event.button !== 0 || window.innerWidth <= 800) return

    event.preventDefault()
    resizingRef.current = true
    setIsResizing(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  async function handleSaveProfile(profile) {
    if (editor?.isMock) {
      const questions = []
      if (profile.area.value === null) questions.push({ message: '방문할 지역을 선택해 주세요.' })
      if (profile.timeWindow.value === null) questions.push({ message: '이용 시간을 입력해 주세요.' })
      return { profile, status: questions.length ? 'NEEDS_INPUT' : 'READY', questions, warnings: [] }
    }

    if (!session || profileSaveRef.current || courseRequestRef.current || adjustmentRequestRef.current) {
      throw new Error('서버 연결 또는 이전 저장이 끝날 때까지 기다려 주세요.')
    }

    profileSaveRef.current = true
    let result
    try {
      result = await saveProfile(session.sessionId, profile, session.profileRevision)
      latestCourseRef.current = null
      setCourseRetry(null)
      setSession((current) => {
        if (current?.sessionId !== session.sessionId) return current
        return {
          ...current,
          latestCourseId: null,
          savedProfile: result.profile,
          profileStatus: result.status,
          profileRevision: result.profileRevision,
          expiresAt: result.sessionExpiresAt,
        }
      })
      setMessages((current) => {
        const updated = { role: 'assistant', profile: result.profile, status: result.status,
          warnings: result.warnings,
          content: ['조건을 저장했어요.', ...result.questions.map((q) => q.message)].join('\n\n') }
        return current.some((message) => message.id === editor?.target)
          ? current.map((message) => message.id === editor?.target ? { ...message, ...updated } : message)
          : [...current, { id: crypto.randomUUID(), ...updated }]
      })
    } catch (error) {
      if ([409, 410].includes(error.status) || !error.status) {
        setSessionError('조건 저장 상태를 확인할 수 없어요. 새 대화를 시작해 주세요.')
      }
      throw error
    } finally {
      profileSaveRef.current = false
    }

    if (editor?.regenerate && result.status === 'READY') {
      const generated = await handleCreateCourse(result)
      if (generated) setEditor(null)
    }
    return result
  }

  function openEditor(target, focusField) {
    if (!session || sessionError || profileSaveRef.current || courseRequestRef.current || adjustmentRequestRef.current || isSending || editor) return
    setEditor({ target, isMock: false, focusField, regenerate: Boolean(focusField) })
  }

  function renderProfileEditor() {
    return (
      <>
        <ProfileEditor
          key={editor.isMock ? 'mock' : 'live'}
          initialProfile={
            editor.isMock
              ? readyMock.profile
              : session?.savedProfile ?? createEmptyProfile()
          }
          isMock={editor.isMock}
          focusField={editor.focusField}
          regenerateOnSave={editor.regenerate}
          capabilities={editor.isMock ? null : session?.capabilities}
          canSave={
            editor.isMock || (Boolean(session) && !isSending && !isCreatingCourse && !sessionError)
          }
          sessionError={editor.isMock ? '' : sessionError}
          onSave={handleSaveProfile}
          onRestart={retrySession}
          onClose={() => setEditor(null)}
        />

        {!editor.isMock && session?.profileStatus === 'READY' && (
          <div className="profile-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => handleCreateCourse()}
              disabled={isCreatingCourse || isSending || isAdjustingCourse || Boolean(sessionError)}
            >
              {isCreatingCourse ? '코스 만드는 중…' : '저장한 조건으로 코스 만들기'}
            </button>
          </div>
        )}
      </>
    )
  }

  function handleNewChat() {
    if (profileSaveRef.current) return
    retrySession()
    setInput('')
    setIsSending(false)
    setSidebarOpen(false)
  }

  function handleSubmit(event) {
    event.preventDefault()
    const text = input.trim()
    if (!text) return
    sendMessage(text)
  }

  async function sendMessage(text) {
    if (!session || sessionError || isSending || profileSaveRef.current || courseRequestRef.current || adjustmentRequestRef.current || editor) return
    profileSaveRef.current = true
    const controller = new AbortController()
    chatAbortRef.current = controller

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      },
    ])

    setInput('')
    setIsSending(true)

    try {
      const response = await sendChat(session.sessionId, text, session.profileRevision, controller.signal)
      if (controller.signal.aborted) return
      latestCourseRef.current = null
      setCourseRetry(null)
      setSession((current) => ({
        ...current,
        latestCourseId: null,
        savedProfile: response.profile,
        profileStatus: response.status,
        profileRevision: response.profileRevision,
        expiresAt: response.sessionExpiresAt,
      }))
      const questions = response.status === 'NEEDS_INPUT'
        ? (response.questions ?? []).slice(0, 2)
        : []

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: [
            response.reply,
            ...questions.map((question) => question.message),
          ].join('\n\n'),
          status: response.status,
          profile: response.profile,
          warnings: response.warnings,
        },
      ])

    } catch (error) {
      if (error.name === 'AbortError') return
      const restart = [409, 410].includes(error.status) || !error.status
      const content = error.status === 429
        ? `요청이 많아요. ${error.retryAfter ?? '잠시'}초 뒤 다시 입력해 주세요.`
        : error.status ? error.message : '연결이 끊겼어요. 저장 여부를 확인할 수 없어 새 대화가 필요해요.'
      if (restart) setSessionError(content)
      setMessages((current) => [...current, {
        id: crypto.randomUUID(), role: 'assistant', content,
        directInput: error.status === 503 || error.status === 422,
      }])
    } finally {
      profileSaveRef.current = false
      chatAbortRef.current = null
      setIsSending(false)
    }
  }

  async function handleCreateCourse(savedProfile = session) {
    if (
      !session ||
      (savedProfile?.status ?? savedProfile?.profileStatus) !== 'READY' ||
      sessionError ||
      profileSaveRef.current ||
      courseRequestRef.current ||
      adjustmentRequestRef.current
    ) {
      return
    }

    const requestedRevision = savedProfile.profileRevision
    const courseProfile = savedProfile.profile ?? savedProfile.savedProfile
    const isInjuryCourse = courseProfile?.mobility?.value?.includes('INJURY') ?? false
    const controller = new AbortController()
    courseRequestRef.current = controller
    setIsCreatingCourse(true)
    latestCourseRef.current = null
    setSession((current) => current?.sessionId === session.sessionId ? { ...current, latestCourseId: null } : current)
    setCourseRetry(null)

    try {
      const response = await createCourse(
        session.sessionId,
        requestedRevision,
        controller.signal,
      )

      if (controller.signal.aborted) return

      const courseMessageId = crypto.randomUUID()
      latestCourseRef.current = response.course ? {
        sessionId: session.sessionId, messageId: courseMessageId,
        profileRevision: requestedRevision, course: response.course,
      } : null
      const isDemo = import.meta.env.DEV &&
        new URLSearchParams(window.location.search).get('qa') === 'course-api'
      setCourseRetry(null)

      setMessages((previous) => [
        ...previous,
        {
          id: courseMessageId,
          role: 'assistant',
          content: response.status === 'INSUFFICIENT_PLACES'
            ? '저장한 조건으로 방문할 수 있는 장소가 부족해요.'
            : '저장한 조건으로 코스를 만들었어요.',
          courseResponse: response,
          requestedRevision,
          isInjuryCourse,
          isMock: isDemo,
        },
      ])
      setSession((current) => current?.sessionId === session.sessionId
        ? { ...current, latestCourseId: response.course?.id ?? null, expiresAt: response.sessionExpiresAt }
        : current)
      return true
    } catch (error) {
      if (!controller.signal.aborted) {
        if ([409, 410].includes(error.status)) {
          setSessionError('코스 생성 상태를 확인할 수 없어요. 새 대화를 시작해 주세요.')
        } else if (!error.status || error.status === 429 || error.status >= 500) {
          setCourseRetry({
            sessionId: session.sessionId,
            profileRevision: requestedRevision,
            status: 'READY',
            profile: courseProfile,
          })
        }
        setMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: error.status
              ? error.message
              : '서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.',
          },
        ])
      }
    } finally {
      if (courseRequestRef.current === controller) {
        courseRequestRef.current = null
        setIsCreatingCourse(false)
      }
    }
    return false
  }

  function handleRecommend() {
    return handleCreateCourse()
  }

  async function handleIncludeUnknown(message) {
    if (!session || sessionError || editor || isSending || profileSaveRef.current ||
        courseRequestRef.current || adjustmentRequestRef.current || unknownRequestRef.current) return
    if (message.requestedRevision !== session.profileRevision ||
        message.id !== messages.findLast((item) => item.courseResponse)?.id) {
      throw new Error('조건이 변경됐어요. 최신 조건으로 코스를 다시 만들어 주세요.')
    }
    const profile = buildInclusionProfile(session)
    unknownRequestRef.current = true
    setIsIncludingUnknown(true)
    try {
      const result = await handleSaveProfile(profile)
      if (result.status !== 'READY' || !result.profile.includeUnknownAccessibility) return
      await handleCreateCourse(result)
    } catch (error) {
      error.userMessage = error.message
      throw error
    } finally {
      unknownRequestRef.current = false
      setIsIncludingUnknown(false)
    }
  }

  async function handleAdjustCourse(message, text) {
    const snapshot = latestCourseRef.current
    if (!session || sessionError || editor || isSending || profileSaveRef.current ||
        courseRequestRef.current || unknownRequestRef.current || adjustmentRequestRef.current ||
        session.capabilities?.supportsCourseAdjustment !== true || !text.trim() ||
        !snapshot || snapshot.sessionId !== session.sessionId || snapshot.messageId !== message.id ||
        snapshot.profileRevision !== session.profileRevision ||
        snapshot.course.id !== message.courseResponse?.course?.id ||
        message.requestedRevision !== session.profileRevision || message.adjustmentBlocked) return false

    const controller = new AbortController()
    adjustmentRequestRef.current = controller
    setIsAdjustingCourse(true)
    setMessages((current) => current.map((item) => item.id === message.id
      ? { ...item, adjustmentError: '' } : item))
    try {
      const response = await adjustCourse(snapshot.sessionId, snapshot.course.id,
        snapshot.profileRevision, text.trim(), controller.signal)
      if (controller.signal.aborted || latestCourseRef.current !== snapshot) return false
      const applied = acceptAdjustmentResponse(snapshot.course, snapshot.course.id,
        snapshot.profileRevision, response)
      if (applied.ignored) return false
      latestCourseRef.current = { ...snapshot, course: applied.course }
      setMessages((current) => current.map((item) => item.id === snapshot.messageId ? {
        ...item,
        content: response.status === 'SUCCESS' ? '코스를 수정했어요.'
          : response.status === 'NEEDS_INPUT' ? '수정 전에 추가 확인이 필요해요.' : '수정을 적용하지 않았어요.',
        courseResponse: { ...response, course: applied.course },
        adjustmentResponse: response,
        beforeAdjustment: snapshot.course,
        adjustmentError: '',
        adjustmentBlocked: false,
      } : item))
      setSession((current) => current?.sessionId === snapshot.sessionId
        ? { ...current, latestCourseId: applied.course.id, expiresAt: response.sessionExpiresAt } : current)
      return true
    } catch (error) {
      if (controller.signal.aborted || latestCourseRef.current !== snapshot) return false
      const recovery = adjustmentNeedsRecovery(error)
      if (recovery) latestCourseRef.current = null
      setMessages((current) => current.map((item) => item.id === snapshot.messageId ? {
        ...item, adjustmentResponse: null, beforeAdjustment: null,
        adjustmentError: adjustmentErrorMessage(error), adjustmentBlocked: recovery,
      } : item))
      if (recovery) setSession((current) => current?.sessionId === snapshot.sessionId
        ? { ...current, latestCourseId: null } : current)
      if (error.status === 410 || error.code === 'SESSION_EXPIRED') {
        setSessionError('대화가 만료됐어요. 새 대화를 시작해 주세요.')
      }
      return false
    } finally {
      if (adjustmentRequestRef.current === controller) {
        adjustmentRequestRef.current = null
        setIsAdjustingCourse(false)
      }
    }
  }

  async function handleRetryCourse() {
    if (!courseRetry || editor || isSending || isIncludingUnknown ||
        courseRetry.sessionId !== session?.sessionId ||
        courseRetry.profileRevision !== session?.profileRevision) return
    return handleCreateCourse(courseRetry)
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  const composer = (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="부산에서 어떤 하루를 보내고 싶으세요?"
        aria-label="여행 조건 입력"
        rows={1}
        maxLength={1000}
        disabled={isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || !session || Boolean(sessionError) || Boolean(editor)}
      />
      <div className="composer-bottom">
        <span>✦ BusanFit AI</span>
        <button
          type="submit"
          className="send-button"
          aria-label="메시지 전송"
          disabled={!input.trim() || isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || !session || Boolean(sessionError) || Boolean(editor)}
        >
          ↑
        </button>
      </div>
    </form>
  )

  return (
    <div className="app-shell">
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        width={sidebarWidth}
        onResizeStart={handleResizeStart}
      />

      <main className="main-panel">
        <header className="topbar">
          <button
            type="button"
            className="icon-button menu-button"
            aria-label="사이드바 열기"
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>

        </header>

        {!isQaEditor && <div className="chat-notice" role="status">
          <span>개발 검증 중 · 개인정보가 없는 가상 조건만 입력해 주세요.</span>
          {sessionError ? <><p>{sessionError}</p><button type="button" onClick={handleNewChat}>새 대화 시작</button></>
            : !session ? <p>서버 연결 중…</p> : <button type="button" disabled={isSending || isAdjustingCourse || Boolean(editor)} onClick={() => openEditor('manual')}>조건 직접 입력</button>}
        </div>}

        {isQaEditor || editor?.target === 'manual' ? (
          <div className="profile-editor-page">{renderProfileEditor()}</div>
        ) : !hasMessages ? (
          <div className="welcome-layout">
            <div className="welcome-content">
              <div className="welcome-symbol">✦</div>
              <h1>어디로 떠나볼까요?</h1>
              <p>
                부산에서 보내고 싶은 하루를 이야기해 주세요.
                <br />
                여행 조건부터 일정 계획까지 함께 준비할게요.
              </p>

              {composer}

              <div className="example-prompts">
                <button
                  type="button"
                  onClick={() => setInput('해운대에서 친구랑 놀고 싶어')}
                >
                  해운대에서 친구랑 놀고 싶어
                </button>
                <button
                  type="button"
                  onClick={() => setInput('광안리에서 오후에 데이트하고 싶어')}
                >
                  광안리에서 오후에 데이트하고 싶어
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="conversation-scroll">
              <div className="conversation">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`message-row ${message.role}`}
                  >
                    {message.role === 'assistant' && (
                      <div className="assistant-avatar">✦</div>
                    )}

                    <div className="message-body">
                      <div className="message-bubble">
                        {message.content}
                      </div>

                      {message.isMock && (
                        <span className="message-caption">가상 응답</span>
                      )}

                      {message.warnings?.map((warning, index) => <p className="chat-warning" role="status" key={`${warning.code}-${index}`}>{warning.message}</p>)}

                      {message.directInput && <button type="button" disabled={isSending || isAdjustingCourse} onClick={() => openEditor(message.id)}>조건 카드에 직접 입력</button>}

                      {message.profile && message.id === messages.findLast((item) => item.profile)?.id && (
                        editor?.target === message.id ? renderProfileEditor() : (
                          <ConditionCard
                            profile={message.profile}
                            ready={message.status === 'READY'}
                            disabled={isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || Boolean(sessionError)}
                            onRecommend={handleRecommend}
                            onEdit={() => openEditor(message.id)}
                          />
                        )
                      )}

                      {message.id === messages.findLast((item) => item.profile)?.id && message.warnings?.some((w) => w.code === 'UNSUPPORTED_TRANSPORT') && (
                        <button type="button" disabled={isSending || isCreatingCourse || Boolean(editor)} onClick={() => sendMessage('도보로 이동할게요')}>도보로 이동할게요</button>
                      )}

                      {editor?.target === message.id && !message.profile && renderProfileEditor()}

                      {(message.showCoursePlaceholder || message.courseResponse) && (
                        <CourseTimeline
                          courseResponse={message.courseResponse}
                          adjustment={message.adjustmentResponse}
                          isInjury={message.isInjuryCourse ?? false}
                          supportsUnknownInclusion={session?.capabilities?.supportsUnknownAccessibilityInclusion === true}
                          onIncludeUnknown={() => handleIncludeUnknown(message)}
                          isMock={message.isMock}
                          onEditSuggestion={message.courseResponse
                            ? (suggestion) => openEditor(message.id, suggestion.field)
                            : undefined}
                          suggestionsDisabled={
                            Boolean(editor) || isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || Boolean(sessionError)
                            || message.id !== messages.findLast((item) => item.courseResponse)?.id
                            || message.requestedRevision !== session?.profileRevision
                          }
                        />
                      )}
                      {message.courseResponse?.course && (
                        <CourseAdjustmentResult response={message.adjustmentResponse}
                          before={message.beforeAdjustment} error={message.adjustmentError} />
                      )}
                      {message.courseResponse?.course && message.id === messages.findLast((item) => item.courseResponse)?.id && (
                        <>
                          {session?.capabilities?.supportsCourseAdjustment === true && (
                            <CourseAdjustmentPanel
                              key={`${session.sessionId}-${message.id}`}
                              onSubmit={(text) => handleAdjustCourse(message, text)}
                              busy={isAdjustingCourse}
                              disabled={Boolean(editor) || isSending || isCreatingCourse || isIncludingUnknown ||
                                Boolean(sessionError) || message.adjustmentBlocked ||
                                message.requestedRevision !== session.profileRevision ||
                                message.courseResponse.course.id !== session.latestCourseId}
                              questions={message.adjustmentResponse?.questions ?? []}
                            />
                          )}
                          {message.adjustmentResponse?.questions?.some((question) => question.field.startsWith('profile.')) && (
                            <button type="button" className="profile-secondary"
                              disabled={isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || Boolean(editor) || Boolean(sessionError)}
                              onClick={() => openEditor(message.id, message.adjustmentResponse.questions.find((question) => question.field.startsWith('profile.')).field.slice(8))}>
                              조건 카드에서 변경
                            </button>
                          )}
                          {message.adjustmentBlocked && !sessionError && (
                            <button type="button" className="profile-secondary"
                              disabled={isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || Boolean(editor)}
                              onClick={handleRecommend}>저장한 조건으로 새 코스 만들기</button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                ))}

                {courseRetry && courseRetry.sessionId === session?.sessionId &&
                  courseRetry.profileRevision === session?.profileRevision && (
                  <div className="condition-card" role="status">
                    <p>저장한 조건은 유지돼요. 조건을 다시 저장하지 않고 코스 생성만 재시도할 수 있어요.</p>
                    <button type="button" className="profile-secondary"
                      disabled={Boolean(editor) || isSending || isCreatingCourse || isIncludingUnknown || isAdjustingCourse || Boolean(sessionError)}
                      onClick={handleRetryCourse}>
                      코스 생성만 다시 시도
                    </button>
                  </div>
                )}

                {isSending && (
                  <div className="message-row assistant">
                    <div className="assistant-avatar">✦</div>
                    <div
                      className="typing-indicator"
                      aria-label="응답 생성 중"
                    >
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            </div>

            <div className="bottom-composer">
              {composer}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App
