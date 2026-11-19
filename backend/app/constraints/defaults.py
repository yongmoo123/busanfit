"""FR-005 defaults; no place lookup, retrieval, scheduling or DB access."""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

CONFIG = json.loads((Path(__file__).resolve().parents[3] / 'config/defaults.json').read_text(encoding='utf-8'))
STAY_MINUTES = MappingProxyType(CONFIG['stayMinutes'])


def positive_minutes(value):
    if type(value) is not int or value <= 0:
        raise ValueError('stay minutes must be a positive integer')
    return value


@dataclass(frozen=True)
class StayDuration:
    minutes: int
    source: Literal['USER', 'DEFAULT']


def resolve_stay(category: str, *, facility_minutes: int | None = None,
                 user_minutes: int | None = None,
                 defaults: Mapping[str, int] = STAY_MINUTES) -> StayDuration:
    """Receive normalized integer durations from #7/#22/#23; never parse raw data.

    Explicit USER duration > facility/TourAPI duration > category setting. A
    facility duration selected by the server is still a DEFAULT, not USER.
    """
    if category not in STAY_MINUTES:
        raise ValueError('unknown place category')
    # Reject invalid known inputs rather than quietly treating 0 as unknown.
    if facility_minutes is not None:
        positive_minutes(facility_minutes)
    if user_minutes is not None:
        return StayDuration(positive_minutes(user_minutes), 'USER')
    if facility_minutes is not None:
        return StayDuration(facility_minutes, 'DEFAULT')
    return StayDuration(positive_minutes(defaults[category]), 'DEFAULT')


def apply_walk_default(profile: dict, capabilities, pending: dict) -> dict:
    """PUT defaults after input validation; an unresolved mode is never accepted."""
    result = deepcopy(profile)
    transport = result['transport']
    if (transport['value'] is None and transport['source'] == 'UNSET'
            and 'transport' not in pending
            and 'transport' in capabilities.supportedProfileFields
            and 'WALK' in capabilities.supportedTransports):
        result['transport'] = {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}
    # Budget remains null/UNSET: unlimited is not a zero-price estimate.
    return result
