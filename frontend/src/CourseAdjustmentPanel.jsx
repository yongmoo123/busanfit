import { useId, useRef, useState } from 'react'
import SuggestionChips from './SuggestionChips.jsx'
import './CourseAdjustment.css'

const examples = [
  { id: 'remove', label: '2번 빼줘', message: '2번 빼줘' },
  { id: 'replace', label: '2번 다른 카페로 바꿔줘', message: '2번 다른 카페로 바꿔줘' },
  { id: 'extend', label: '2번에 30분 더 머물래', message: '2번에 30분 더 머물래' },
]

export default function CourseAdjustmentPanel({ onSubmit, busy = false, disabled = false, questions = [] }) {
  const [message, setMessage] = useState('')
  const inputId = useId()
  const input = useRef(null)
  const locked = busy || disabled

  async function submit(event) {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || locked) return
    // Parent guards duplicate submissions synchronously, before React re-renders.
    const accepted = await onSubmit(trimmed)
    if (accepted) setMessage('')
  }

  return (
    <section className="course-adjustment" aria-label="코스 수정" aria-busy={busy}>
      <h2>코스를 어떻게 바꿀까요?</h2>
      <p>장소 빼기·바꾸기·체류 늘리기를 요청할 수 있어요. 조건을 만족할 때만 변경해요.</p>
      {questions.length > 0 && (
        <div className="adjustment-question" role="status">
          <h3>추가로 확인해 주세요</h3>
          {questions.map((question, index) => <p key={`${question.field}-${index}`}>{question.message}</p>)}
          <p>아래 입력창에 답해 주세요.</p>
        </div>
      )}
      <SuggestionChips
        suggestions={examples}
        disabled={locked}
        onSelect={(example) => { setMessage(example.message); input.current?.focus() }}
      />
      <form onSubmit={submit}>
        <label htmlFor={inputId}>{questions.length ? '질문에 답하거나 수정 내용을 입력해 주세요' : '수정 내용'}</label>
        <textarea
          ref={input} id={inputId} value={message} maxLength={1000} rows={3}
          placeholder="예: 2번 빼줘" disabled={locked}
          onChange={(event) => setMessage(event.target.value)}
        />
        <button type="submit" disabled={locked || !message.trim()}>
          {busy ? '수정 확인 중…' : '수정 요청'}
        </button>
      </form>
      {busy && <p role="status">수정할 수 있는지 확인하고 있어요. 기존 코스는 유지하고 있어요.</p>}
      {disabled && !busy && <p>최신 코스를 준비한 뒤 수정할 수 있어요.</p>}
    </section>
  )
}
