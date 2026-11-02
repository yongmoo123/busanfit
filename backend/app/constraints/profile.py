"""Deterministic card validation; no defaults or constraint relaxation."""
from datetime import timedelta, timezone
from app.api.profile_models import Profile
from app.api.session_models import Capabilities


class ProfileError(Exception):
    def __init__(self, code: str, field: str, reason: str):
        super().__init__(code)
        self.code = code
        # Static field/reason only; never reflect user input.
        self.details = [{'field': field, 'reason': reason}]


def validate_profile(profile: Profile, previous: dict | None, capabilities: Capabilities):
    values = profile.model_dump(mode='json')
    for name, condition in values.items():
        if name == 'includeUnknownAccessibility':
            continue
        value, source = condition['value'], condition['source']
        if (value is None) != (source == 'UNSET'):
            raise ProfileError('INVALID_PROFILE', name, 'null과 UNSET은 함께 지정해야 합니다.')
        if name in ('area', 'timeWindow') and condition['strength'] != 'HARD':
            raise ProfileError('INVALID_PROFILE', name, '지역과 시간은 HARD여야 합니다.')
        if isinstance(value, list) and len(value) != len(set(value)):
            raise ProfileError('INVALID_PROFILE', name, '중복 항목을 제거해 주세요.')
        # Existing server defaults may be carried forward, but not invented by a card.
        if source == 'DEFAULT' and (previous is None or condition != previous.get(name)):
            raise ProfileError('INVALID_PROFILE', name, '카드에서 지정하거나 변경한 값의 출처는 USER여야 합니다.')

    window = profile.timeWindow.value
    if window is not None:
        seoul = timezone(timedelta(hours=9))
        if window.startAt >= window.endAt:
            raise ProfileError('INVALID_PROFILE', 'timeWindow', '종료 시각은 시작 시각보다 늦어야 합니다.')
        if window.startAt.astimezone(seoul).date() != window.endAt.astimezone(seoul).date():
            raise ProfileError('INVALID_PROFILE', 'timeWindow', '한국 시각 기준 같은 날짜만 지원합니다.')
    budget = profile.budget.value
    if budget and len(budget.includes) != len(set(budget.includes)):
        raise ProfileError('INVALID_PROFILE', 'budget', '예산 포함 항목은 중복될 수 없습니다.')

    for name, condition in values.items():
        if name == 'includeUnknownAccessibility':
            if condition and not capabilities.supportsUnknownAccessibilityInclusion:
                raise ProfileError('UNSUPPORTED_CONSTRAINT', name, '현재 지원하지 않는 조건입니다.')
            continue
        value = condition['value']
        if value is None or value == []:
            continue
        supported = name in capabilities.supportedProfileFields
        if name == 'area':
            supported = supported and value in capabilities.supportedAreas
        if name == 'transport':
            supported = supported and value in capabilities.supportedTransports
        if not supported:
            raise ProfileError('UNSUPPORTED_CONSTRAINT', name, '현재 지원하지 않는 조건입니다.')

    questions = []
    if profile.area.value is None:
        questions.append({'field': 'area', 'message': '방문할 지역을 선택해 주세요.'})
    if profile.timeWindow.value is None:
        questions.append({'field': 'timeWindow', 'message': '시작 시각과 종료 시각을 입력해 주세요.'})
    return questions
