import { useEffect, useId, useRef, useState } from 'react'
import SuggestionChips from './SuggestionChips.jsx'

export default function UnknownPlaceSuggestion({ count, disabled = false, onConfirm }) {
  const dialogRef = useRef(null)
  const triggerRef = useRef(null)
  const titleId = useId()
  const descriptionId = useId()
  const [acknowledged, setAcknowledged] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const submittingRef = useRef(false)

  useEffect(() => {
    if (disabled) dialogRef.current?.close()
  }, [disabled])

  if (count <= 0) return null

  function openConfirmation() {
    triggerRef.current = document.activeElement
    setAcknowledged(false)
    setError('')
    dialogRef.current?.showModal()
  }

  async function confirm(event) {
    event.preventDefault()
    if (!acknowledged || disabled || submittingRef.current) return
    submittingRef.current = true
    setIsSubmitting(true)
    setError('')
    try {
      await onConfirm()
      dialogRef.current?.close()
    } catch {
      setError('다시 만들지 못했어요. 조건을 확인하고 다시 시도해 주세요.')
    } finally {
      submittingRef.current = false
      setIsSubmitting(false)
    }
  }

  return (
    <div className="unknown-place-suggestion">
      <p>접근성 정보가 없어 제외된 장소가 {count}곳 있어요.</p>
      <SuggestionChips
        suggestions={[{
          id: 'preview-include-unknown',
          label: '정보가 없는 장소도 포함해서 다시 만들까요?',
        }]}
        disabled={disabled || isSubmitting}
        onSelect={openConfirmation}
      />
      <dialog
        ref={dialogRef}
        className="unknown-confirmation"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onCancel={(event) => { if (submittingRef.current) event.preventDefault() }}
        onClose={() => triggerRef.current?.focus()}
      >
        <form onSubmit={confirm}>
          <h3 id={titleId}>접근성 정보가 없는 장소 포함</h3>
          <p id={descriptionId}>
            휠체어·유모차 이용 가능 여부가 확인되지 않은 장소가 포함될 수 있어요.
            방문 전 장소에 직접 확인해 주세요.
          </p>
          <p>이동제약 조건은 유지하며, 포함된 장소에 미확인 경고를 표시해요.</p>
          <label className="unknown-acknowledgement">
            <input
              type="checkbox"
              checked={acknowledged}
              disabled={isSubmitting}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            <span>접근성 정보가 확인되지 않았음을 이해하고 포함을 요청합니다.</span>
          </label>
          {error && <p role="alert">{error}</p>}
          <div className="unknown-actions">
            <button type="button" disabled={isSubmitting} onClick={() => dialogRef.current?.close()}>취소</button>
            <button type="submit" disabled={!acknowledged || disabled || isSubmitting}>
              {isSubmitting ? '다시 만드는 중…' : '포함해서 다시 만들기'}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  )
}
