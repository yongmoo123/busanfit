import settings from '../../config/defaults.json'

export const stayDefaults = settings.stayMinutes
export const injuryDefaults = settings.injury

export function budgetLabel(condition) {
  return condition.value === null ? '제한 없음' : `${condition.value.amount.toLocaleString('ko-KR')}원`
}
