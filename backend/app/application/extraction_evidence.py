"""FR-002 High guards: schema-valid AI values still need user-message evidence.

This is not a complete natural-language parser. It only removes unsupported
time windows and family subfields before the existing session/default policy.
Raw text and evidence matches are never returned, retained, or logged.
"""
from copy import deepcopy
import re


_CLOCK = (r'(?<![\d:])(?:(?:오전|오후|아침|낮|저녁|밤)\s*)?'
          r'\d{1,2}\s*(?:시(?:\s*\d{1,2}\s*분)?|:\d{2})(?![\d:])')
_RANGE = re.compile(_CLOCK + r'\s*(?:부터|에서|[~～〜–—-])\s*' + _CLOCK)
_END = re.compile(_CLOCK + r'\s*(?:쯤|정도)?\s*까지')
_DURATION = re.compile(r'(?<!\d)(?:\d+(?:\.\d+)?|한|두|세|네|다섯|여섯)\s*(?:시간|분)\s*(?:동안|정도|쯤|놀|머무|보낼|코스|만)')
_TIME_MENTION = re.compile(_CLOCK + r'|시간|오늘|내일|모레|[월화수목금토일]요일|오전|오후|저녁|아침')
_KOREAN_COUNTS = {'한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '셋': 3,
                  '네': 4, '넷': 4, '다섯': 5, '여섯': 6, '일곱': 7, '여덟': 8, '아홉': 9, '열': 10}
_COUNT = re.compile(r'(?<!\d)(\d+)\s*(?:명|사람)|'
    r'(' + '|'.join(sorted(_KOREAN_COUNTS, key=len, reverse=True)) + r')\s*(?:명|사람|이서|이\s*(?:가|갈|갑|놀))')
_INFANT = r'(?:영유아|영아|아기(?!자기)|애기|돌\s*(?:지난|전|안\s*된)\s*아이)'
_NO_INFANT = re.compile(_INFANT + r'(?:들)?\s*(?:는|가|도|를|은|이)?\s*'
                       r'(?:없|안\s*(?:가|갈|와|데려|동반)|동반하지\s*않|함께하지\s*않|없이)')


def _has_end_evidence(message):
    def positive(match):
        return not re.match(r'\s*(?:까지)?\s*(?:는|은|이|가)?\s*(?:아니|아닌|말고|안\s*(?:돼|되)|못|미정|모르)',
                            message[match.end():])
    return (any(positive(match) for regex in (_RANGE, _END) for match in regex.finditer(message))
            or bool(re.search(_CLOCK, message) and _DURATION.search(message)))


def _count_is_supported(message, value):
    matches = list(_COUNT.finditer(message))
    # Multiple group counts require interpretation of a total; do not guess one.
    if len(matches) != 1:
        return False
    match = matches[0]
    if re.match(r'\s*(?:이|은|는|도)?\s*(?:아니|말고|더|추가|빼|제외)', message[match.end():]):
        return False
    count = int(match[1]) if match[1] else _KOREAN_COUNTS[match[2]]
    return value == count


def _infant_evidence(message):
    negative = list(_NO_INFANT.finditer(message))
    positive = [m for m in re.finditer(_INFANT, message)
                if not any(n.start() <= m.start() < n.end() for n in negative)]
    if negative and positive:
        return None  # Conflicting clauses need confirmation, not an inferred bool.
    return False if negative else True if positive else None


def ground_high_risk_fields(message, profile, hints, unconfirmed):
    """Return sanitized copies, retaining only the partial hints needed by DEC-022."""
    profile, hints, unconfirmed = deepcopy(profile), deepcopy(hints), set(unconfirmed)
    window = profile['timeWindow']
    if window['value'] is not None and not _has_end_evidence(message):
        profile['timeWindow'] = {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
        if _TIME_MENTION.search(message):
            unconfirmed.add('timeWindow')

    condition = profile['companions']
    values = {**hints, **(condition['value'] or {})}
    family_denied = bool(re.search(r'가족(?:은|이|이랑|과|하고)?\s*(?:아니|아닌|아님|말고)', message))
    family_mentioned = bool(re.search(r'가족', message)) and not family_denied
    if family_denied and values.get('type') == 'FAMILY':
        condition['value'], condition['source'] = None, 'UNSET'
        unconfirmed.add('companions')
        return profile, {}, unconfirmed
    # A family keyword may be incidental (e.g. "가족 같은 친구"). Only fill
    # a missing type; do not reclassify an explicit non-family AI type.
    if values.get('type') == 'FAMILY' or (family_mentioned and values.get('type') is None):
        if family_mentioned:
            values['type'] = 'FAMILY'
        if values.get('count') is not None and not _count_is_supported(message, values['count']):
            values.pop('count', None)
        evidence = _infant_evidence(message)
        if evidence is None or values.get('hasInfant') != evidence:
            if evidence is not None and values.get('hasInfant') is not None:
                unconfirmed.add('companions')
            values.pop('hasInfant', None)
        if '아이' not in message and not re.search(_INFANT, message):
            values.pop('hasChild', None)
        hints = {key: value for key, value in values.items() if value is not None}
        if all(hints.get(key) is not None for key in ('type', 'count', 'hasInfant')):
            condition['value'] = {key: hints[key] for key in ('type', 'count', 'hasInfant')}
            condition['source'] = 'USER'
        else:
            condition['value'], condition['source'] = None, 'UNSET'
        # No UNCONFIRMED_CHANGE here: partial family hints must reach DEC-022's
        # existing one-time infant question instead of bypassing that policy.
    return profile, hints, unconfirmed
