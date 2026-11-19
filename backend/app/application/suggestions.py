"""FR-014(1): deterministic edit links for applied, editable profile defaults.

This function does not apply defaults, relax constraints, or change the profile.
Call it with the validated profile actually used by a successful course request.
"""
from app.api.course_models import Suggestion
from app.api.profile_models import Profile
from app.api.session_models import Capabilities

# Existing condition-card order, not scoring or a new product priority policy.
# No stay duration, unknown-place inclusion, or weather actions in this scope.
CARD_LABELS = {
    'area': '기본 지역을 확인하거나 직접 선택해 주세요.',
    'transport': '기본 이동수단을 확인하거나 직접 선택해 주세요.',
    'timeWindow': '기본 이용 시간을 확인하거나 직접 수정해 주세요.',
    'mobility': '기본 이동제약을 확인하거나 직접 수정해 주세요.',
    'budget': '기본 예산을 확인하거나 직접 수정해 주세요.',
    'companions': '기본 동행 정보를 확인하거나 직접 수정해 주세요.',
    'indoorPreference': '기본 실내·실외 선호를 확인하거나 직접 선택해 주세요.',
    'excludedCategories': '기본 제외 카테고리를 확인하거나 직접 수정해 주세요.',
    'preferenceTags': '기본 선호 태그를 확인하거나 직접 수정해 주세요.',
}


def build_default_suggestions(profile: Profile, capabilities: Capabilities) -> list[Suggestion]:
    result = []
    for name, label in CARD_LABELS.items():
        condition = getattr(profile, name)
        if (name not in capabilities.supportedProfileFields
                or condition.source != 'DEFAULT' or condition.value is None):
            continue
        if name == 'area' and condition.value not in capabilities.supportedAreas:
            continue
        if name == 'transport' and condition.value not in capabilities.supportedTransports:
            continue
        result.append(Suggestion(id=f'edit-default-{name}', type='EDIT_PROFILE', field=name, label=label))
        if len(result) == 3:
            break
    return result


def build_unknown_accessibility_suggestions(profile: Profile, capabilities: Capabilities, *, eligible: bool):
    """A UI confirmation action, never consent or a profile mutation."""
    if (not capabilities.supportsUnknownAccessibilityInclusion or not eligible
            or profile.includeUnknownAccessibility or not profile.mobility.value
            or profile.mobility.strength != 'HARD'):
        return []
    return [Suggestion(id='include-unknown-accessibility', type='INCLUDE_UNKNOWN_ACCESSIBILITY',
                       label='접근성 정보가 없는 장소도 포함해서 다시 만들까요?',
                       field='includeUnknownAccessibility')]
