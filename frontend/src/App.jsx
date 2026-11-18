
import { useEffect, useRef, useState } from 'react'
import readyMock from './mocks/02-chat.ready.response.json'
import { createSession, saveProfile, sendChatMessage } from './sessionApi.js'
import { createEmptyProfile } from './profile.js'
import ProfileEditor from './ProfileEditor.jsx'
import CourseTimeline from './CourseTimeline.jsx'
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

function ConditionCard({ profile, onRecommend, onEdit }) {
  const timeWindow = profile?.timeWindow?.value
  const budget = profile?.budget?.value

  const items = [
    { label: '여행 지역', value: getAreaName(profile?.area?.value) },
    { label: '이동수단', value: getTransportName(profile?.transport?.value), source: profile?.transport?.source },
    { label: '시작 시간', value: formatDateTime(timeWindow?.startAt) },
    { label: '종료 시간', value: formatDateTime(timeWindow?.endAt) },
    { label: '동행 인원', value: getCompanionsName(profile?.companions?.value) },
    { label: '예산', value: budget == null ? '미입력' : budget.amount.toLocaleString('ko-KR') + '원' },
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
            {item.source === 'DEFAULT' && <span className="profile-default">기본값</span>}
          </div>
        ))}
      </div>

      <div className="profile-actions">
        <button type="button" className="primary-button" onClick={onEdit}>조건 편집</button>
        <button type="button" className="profile-secondary" onClick={onRecommend}>가상 코스 미리보기</button>
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
    chatRequestRef.current?.abort()
    chatRequestRef.current = null
    setIsSending(false)
    sessionRequestRef.current = null
    setSession(null)
    setSessionError('')
    setSessionAttempt((current) => current + 1)
  }

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(getInitialSidebarWidth)
  const [isResizing, setIsResizing] = useState(false)

  const messagesEndRef = useRef(null)
  const chatRequestRef = useRef(null)
  const resizingRef = useRef(false)

  const hasMessages = messages.length > 0

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end',
    })
  }, [messages, isSending])

  useEffect(() => {
    return () => chatRequestRef.current?.abort()
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

    if (!session || profileSaveRef.current || chatRequestRef.current) {
      throw new Error('서버 연결 또는 이전 저장이 끝날 때까지 기다려 주세요.')
    }

    profileSaveRef.current = true
    try {
      const result = await saveProfile(session.sessionId, profile, session.profileRevision)
      setSession((current) => {
        if (current?.sessionId !== session.sessionId) return current
        return {
          ...current,
          savedProfile: result.profile,
          profileRevision: result.profileRevision,
          expiresAt: result.sessionExpiresAt,
        }
      })
      return result
    } finally {
      profileSaveRef.current = false
    }
  }

  function openEditor(target) {
    if (!profileSaveRef.current) setEditor({ target, isMock: false })
  }

  function renderProfileEditor() {
    return (
      <ProfileEditor
        key={editor.isMock ? 'mock' : 'live'}
        initialProfile={editor.isMock ? readyMock.profile : session?.savedProfile ?? createEmptyProfile()}
        isMock={editor.isMock}
        capabilities={editor.isMock ? null : session?.capabilities}
        canSave={editor.isMock || Boolean(session)}
        sessionError={editor.isMock ? '' : sessionError}
        onSave={handleSaveProfile}
        onRestart={retrySession}
        onClose={() => setEditor(null)}
      />
    )
  }

  function handleNewChat() {
    if (profileSaveRef.current) return

    retrySession()
    setEditor(null)
    setMessages([])
    setInput('')
    setSidebarOpen(false)
  }

  async function handleSubmit(event) {
    event.preventDefault()

    const text = input.trim()
    if (!text || chatRequestRef.current || profileSaveRef.current) return

    if (!session) {
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: sessionError || '서버에 연결 중이에요. 잠시 후 다시 보내 주세요.',
          canRestartSession: Boolean(sessionError),
        },
      ])
      return
    }

    const controller = new AbortController()
    chatRequestRef.current = controller
    setIsSending(true)
    setInput('')
    setMessages((previous) => [
      ...previous,
      { id: crypto.randomUUID(), role: 'user', content: text },
    ])

    try {
      const result = await sendChatMessage(
        session.sessionId,
        text,
        session.profileRevision,
        controller.signal,
      )

      if (controller.signal.aborted) return

      setSession((current) => {
        if (current?.sessionId !== session.sessionId) return current

        return {
          ...current,
          savedProfile: result.profile,
          profileRevision: result.profileRevision,
          expiresAt: result.sessionExpiresAt,
        }
      })

      const details = [
        ...(result.questions ?? []),
        ...(result.warnings ?? []),
      ].map((item) => item.message)

      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: [result.reply, ...details].filter(Boolean).join('\n\n'),
          status: result.status,
          profile: result.profile,
          canEditProfile: result.status === 'NEEDS_INPUT',
        },
      ])
    } catch (error) {
      if (controller.signal.aborted) return

      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: error.status
            ? error.message
            : '서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.',
          canEditProfile: error.status === 503,
          canRestartSession: error.status === 410,
        },
      ])
    } finally {
      if (chatRequestRef.current === controller) {
        chatRequestRef.current = null
        setIsSending(false)
      }
    }
  }

  function handleRecommend() {
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '가상 코스 결과를 확인해 보세요.',
        showCoursePlaceholder: true,
        isMock: true,
      },
    ])
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
        disabled={isSending}
      />
      <div className="composer-bottom">
        <span>✦ BusanFit AI</span>
        <button
          type="submit"
          className="send-button"
          aria-label="메시지 전송"
          disabled={!input.trim() || isSending}
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

        {isQaEditor ? (
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

                      {editor?.target === message.id ? (
                        renderProfileEditor()
                      ) : message.status === 'READY' && message.profile ? (
                        <ConditionCard
                          profile={message.profile}
                          onRecommend={handleRecommend}
                          onEdit={() => openEditor(message.id)}
                        />
                      ) : message.canEditProfile ? (
                        <button
                          type="button"
                          className="profile-secondary"
                          onClick={() => openEditor(message.id)}
                        >
                          조건 직접 입력
                        </button>
                      ) : null}

                      {message.canRestartSession && (
                        <button
                          type="button"
                          className="profile-secondary"
                          onClick={retrySession}
                        >
                          새 세션 시작
                        </button>
                      )}

                      {message.showCoursePlaceholder && (
                        <CourseTimeline />
                      )}
                    </div>
                  </div>
                ))}

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
