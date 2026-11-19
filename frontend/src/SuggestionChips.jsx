import './SuggestionChips.css'

export default function SuggestionChips({ suggestions = [], disabled = false, onSelect }) {
  if (suggestions.length === 0) return null

  return (
    <div className="suggestion-chips" role="group" aria-label="코스 조정 제안">
      {suggestions.slice(0, 3).map((suggestion) => (
        <button
          key={suggestion.id}
          type="button"
          className="suggestion-chip"
          disabled={disabled}
          onClick={() => onSelect(suggestion)}
        >
          {suggestion.label}
        </button>
      ))}
    </div>
  )
}
