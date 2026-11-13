
import { useEffect, useRef, useState } from 'react'
import readyMock from './mocks/02-chat.ready.response.json'
import { createSession, saveProfile, sendChat, deleteSession } from './sessionApi.js'
import { createEmptyProfile } from './profile.js'
import ProfileEditor from './ProfileEditor.jsx'
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

function ConditionCard({ profile, onRecommend, onEdit, ready }) {
  const timeWindow = profile?.timeWindow?.value
  const budget = profile?.budget?.value

  const items = [
    { field: 'area', label: '여행 지역', value: getAreaName(profile?.area?.value) },
    { field: 'transport', label: '이동수단', value: getTransportName(profile?.transport?.value) },
    { field: 'timeWindow', label: '시작 시간', value: formatDateTime(timeWindow?.startAt) },
    { field: 'timeWindow', label: '종료 시간', value: formatDateTime(timeWindow?.endAt) },
    { field: 'companions', label: '동행 인원', value: getCompanionsName(profile?.companions?.value) },
    { field: 'budget', label: '예산', value: budget == null ? '미입력' : budget.amount.toLocaleString('ko-KR') + '원' },
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
            {profile?.[item.field]?.source === 'DEFAULT' && <span className="profile-default">기본값</span>}
            {profile?.[item.field]?.value !== null && <span className="condition-strength">{profile?.[item.field]?.strength === 'HARD' ? '필수' : '선호'}</span>}
          </div>
        ))}
      </div>

      <div className="profile-actions">
        <button type="button" className="primary-button" onClick={onEdit}>조건 편집</button>
        <button type="button" className="profile-secondary" disabled={!ready} onClick={onRecommend}>가상 코스 미리보기</button>
      </div>
    </div>
  )
}

function CoursePlaceholder() {
  return (
    <div className="course-placeholder">
      <div className="course-placeholder-icon">◇</div>
      <div>
        <h3>추천 코스 화면 준비 중</h3>
        <p>
          실제 장소와 이동 경로를 포함한 추천 결과는
          코스 API 연동 후 제공될 예정이에요.
        </p>
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
    if (profileSaveRef.current) return
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

    if (!session || profileSaveRef.current) {
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
      setMessages((current) => {
        const updated = { role: 'assistant', profile: result.profile, status: result.status,
          warnings: result.warnings,
          content: ['조건을 저장했어요.', ...result.questions.map((q) => q.message)].join('\n\n') }
        return current.some((message) => message.id === editor?.target)
          ? current.map((message) => message.id === editor?.target ? { ...message, ...updated } : message)
          : [...current, { id: crypto.randomUUID(), ...updated }]
      })
      return result
    } catch (error) {
      if ([409, 410].includes(error.status) || !error.status) {
        setSessionError('조건 저장 상태를 확인할 수 없어요. 새 대화를 시작해 주세요.')
      }
      throw error
    } finally {
      profileSaveRef.current = false
    }
  }

  function openEditor(target) {
    if (!profileSaveRef.current && !isSending) setEditor({ target, isMock: false })
  }

  function renderProfileEditor() {
    return (
      <ProfileEditor
        key={editor.isMock ? 'mock' : 'live'}
        initialProfile={editor.isMock ? readyMock.profile : session?.savedProfile ?? createEmptyProfile()}
        isMock={editor.isMock}
        canSave={editor.isMock || (Boolean(session) && !isSending && !sessionError)}
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
    if (!session || sessionError || isSending || profileSaveRef.current || editor) return
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
      setSession((current) => ({ ...current, savedProfile: response.profile,
        profileRevision: response.profileRevision, expiresAt: response.sessionExpiresAt }))
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

  function handleRecommend() {
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '여행 코스 추천 기능은 현재 준비 중이에요.',
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
        maxLength={1000}
        disabled={isSending || !session || Boolean(sessionError) || Boolean(editor)}
      />
      <div className="composer-bottom">
        <span>✦ BusanFit AI</span>
        <button
          type="submit"
          className="send-button"
          aria-label="메시지 전송"
          disabled={!input.trim() || isSending || !session || Boolean(sessionError) || Boolean(editor)}
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
          <span>개발 검증 중 · 가상 시나리오만 입력해 주세요. 코스 추천은 준비 중입니다.</span>
          {sessionError ? <><p>{sessionError}</p><button type="button" onClick={handleNewChat}>새 대화 시작</button></>
            : !session ? <p>서버 연결 중…</p> : <button type="button" disabled={isSending || Boolean(editor)} onClick={() => openEditor('manual')}>조건 직접 입력</button>}
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

                      {message.directInput && <button type="button" disabled={isSending} onClick={() => openEditor(message.id)}>조건 카드에 직접 입력</button>}

                      {message.profile && message.id === messages.findLast((item) => item.profile)?.id && (
                        editor?.target === message.id ? renderProfileEditor() : (
                          <ConditionCard
                            profile={message.profile}
                            ready={message.status === 'READY'}
                            onRecommend={handleRecommend}
                            onEdit={() => openEditor(message.id)}
                          />
                        )
                      )}

                      {message.id === messages.findLast((item) => item.profile)?.id && message.warnings?.some((w) => w.code === 'UNSUPPORTED_TRANSPORT') &&
                        <button type="button" disabled={isSending || Boolean(editor)} onClick={() => sendMessage('도보로 이동할게요')}>도보로 이동할게요</button>}

                      {editor?.target === message.id && !message.profile && renderProfileEditor()}

                      {message.showCoursePlaceholder && (
                        <CoursePlaceholder />
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
