"""DEC-002/020 normalization. Copies input; never invents an infant absence."""
from copy import deepcopy


STROLLER_MESSAGE = '유모차 조건은 자동으로 넣지 않았어요. 필요하면 조건 카드에서 추가해 주세요.'


def normalize_mobility(profile: dict, *, has_infant: bool | None = None) -> tuple[dict, list[dict]]:
    """Apply after USER updates, before capability checks and persistence.

    A partial companion hint may provide has_infant without inventing count/type.
    None means unknown, not false. Source belongs to the whole mobility list.
    """
    result = deepcopy(profile)
    companions = result['companions']['value']
    infant = has_infant if has_infant is not None else (
        companions['hasInfant'] if companions is not None else None)
    mobility = result['mobility']
    warnings = []
    if infant is True:
        if mobility['source'] == 'UNSET' and mobility['value'] is None:
            result['mobility'] = {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
        elif mobility['source'] == 'USER' and 'STROLLER' not in (mobility['value'] or []):
            warnings.append({'code': 'STROLLER_NOT_APPLIED', 'message': STROLLER_MESSAGE, 'placeIds': []})
    elif infant is False and mobility['source'] == 'DEFAULT' and 'STROLLER' in (mobility['value'] or []):
        remaining = [value for value in mobility['value'] if value != 'STROLLER']
        result['mobility'] = {'value': remaining or None,
                              'source': 'DEFAULT' if remaining else 'UNSET',
                              'strength': mobility['strength']}
    return result, warnings
