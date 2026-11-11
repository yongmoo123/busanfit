"""DEC-019~021 state transitions; no HTTP, provider calls or raw-message storage."""
from copy import deepcopy
from dataclasses import dataclass
from app.api.profile_models import Profile
from app.constraints.profile import validate_profile
from app.application.extraction import Analysis, blank_profile


TIMEOUT_MESSAGE = '응답이 늦어 일부 조건을 확인하지 못했어요. 조건 카드에서 확인해 주세요.'
FIELD_ORDER = list(blank_profile())[:-1]


def warning(code, message):
    return {'code': code, 'message': message, 'placeIds': []}


def normalize(profile, hints):
    # The implementation is owned by PR #17. Import only when the policy runs;
    # the integration tests also verify both PRs composed without merging them.
    from app.constraints.mobility import normalize_mobility
    return normalize_mobility(profile, has_infant=hints.get('hasInfant'))


def questions_for(profile, pending):
    fields = [name for name in ('area', 'timeWindow') if profile[name]['value'] is None]
    fields += [name for name in FIELD_ORDER if name in pending and name not in fields]
    messages = {'area': '방문할 지역을 선택해 주세요.',
                'timeWindow': '시작 시각과 종료 시각을 입력해 주세요.'}
    return [{'field': name, 'message': (
        '요청한 이동수단은 아직 지원하지 않아요. 지원되는 이동수단을 조건 카드에서 선택해 주세요.'
        if pending.get(name) == 'UNSUPPORTED_TRANSPORT' else
        messages.get(name, '조건 카드에서 이 항목을 확인해 주세요.'))} for name in fields[:2]]


def pending_warnings(pending):
    result = []
    if 'UNSUPPORTED_TRANSPORT' in pending.values():
        result.append(warning('UNSUPPORTED_TRANSPORT', '요청한 이동수단은 아직 지원하지 않아요.'))
    if 'UNCONFIRMED_CHANGE' in pending.values():
        result.append(warning('UNCONFIRMED_CHANGE', '확인하지 못한 조건이 있어요. 조건 카드에서 확인해 주세요.'))
    return result


@dataclass(repr=False)
class PolicyResult:
    profile: Profile
    pending: dict
    hints: dict
    questions: list
    warnings: list
    unavailable: bool = False


def analyze_chat(current, analysis: Analysis, capabilities):
    profile = deepcopy(current.profile) if current.profile is not None else blank_profile()
    pending = deepcopy(current.pending_fields)
    hints = deepcopy(current.companion_hints)
    for name in FIELD_ORDER:
        extracted = analysis.profile[name]
        if name in analysis.unconfirmed_fields:
            pending[name] = 'UNCONFIRMED_CHANGE'
            continue
        if extracted['value'] is None:
            continue
        # Absent-field defaults cannot replace any previously selected value or
        # silently accept an unresolved unsupported transport request.
        if extracted['source'] == 'DEFAULT':
            if profile[name]['value'] is not None or name in pending:
                continue
            if name != 'transport' or extracted['value'] not in capabilities.supportedTransports:
                continue
        if name == 'transport' and (name not in capabilities.supportedProfileFields
                                     or extracted['value'] not in capabilities.supportedTransports):
            pending[name] = 'UNSUPPORTED_TRANSPORT'
            continue
        value = deepcopy(extracted)
        if profile[name]['value'] is not None and profile[name]['strength'] == 'HARD' and value['strength'] == 'SOFT':
            value['strength'] = 'HARD'
        if name == 'mobility' and value['value']:
            # Mentioning another restriction is additive; only explicit USER []
            # or the whole-replacement card can remove existing restrictions.
            value['value'] = list(dict.fromkeys((profile[name]['value'] or []) + value['value']))
            value['strength'] = 'HARD'
        profile[name] = value
        if value['source'] == 'USER':
            pending.pop(name, None)

    if 'companions' not in analysis.unconfirmed_fields:
        hints.update(analysis.companion_hints)
        if analysis.profile['companions']['value'] is not None:
            hints = deepcopy(profile['companions']['value'])
        elif hints:
            existing = profile['companions']['value']
            combined = {**(existing or {}), **hints}
            if all(name in combined for name in ('type', 'count', 'hasInfant')):
                profile['companions'] = {'value': combined, 'source': 'USER', 'strength': 'SOFT'}
                hints = combined
                pending.pop('companions', None)
            else:
                pending['companions'] = 'UNCONFIRMED_CHANGE'

    profile, warnings = normalize(profile, hints)
    typed = Profile.model_validate(profile)
    # Same semantic and capability validation as PUT, after server defaults.
    validate_profile(typed, profile, capabilities)
    unavailable = analysis.fallback and all(profile[name]['value'] is None for name in ('area', 'timeWindow'))
    if analysis.fallback:
        warnings.append(warning('AI_FALLBACK', TIMEOUT_MESSAGE if analysis.failure == 'TIMEOUT'
                                else '규칙 파서로 처리했어요. 조건을 확인해 주세요.'))
    warnings += pending_warnings(pending)
    return PolicyResult(typed, pending, hints, questions_for(profile, pending), warnings, unavailable)


def replace_card(current, profile: Profile, capabilities):
    values = profile.model_dump(mode='json')
    validate_profile(profile, current.profile, capabilities)
    pending = deepcopy(current.pending_fields)
    # Only the displayed questions and actually edited fields can be confirmed.
    # A full-profile echo must not erase questions which were never displayed.
    displayed = {q['field'] for q in questions_for(current.profile or blank_profile(), pending)}
    for name in list(pending):
        condition = values[name]
        changed = current.profile is None or condition != current.profile[name]
        if condition['source'] == 'USER' and condition['value'] is not None and (name in displayed or changed):
            pending.pop(name)
    hints = deepcopy(values['companions']['value'] or {})
    values, warnings = normalize(values, hints)
    typed = Profile.model_validate(values)
    validate_profile(typed, values, capabilities)
    return PolicyResult(typed, pending, hints, questions_for(values, pending),
                        warnings + pending_warnings(pending))
