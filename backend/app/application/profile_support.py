"""Enable only verified #22 fields after composition-root connection succeeds."""
from dataclasses import dataclass, field
import json
from typing import get_args

from app.api.profile_models import Area
from app.api.session_models import Capabilities

INITIAL_FIELDS = ('area', 'timeWindow', 'transport', 'mobility', 'companions', 'excludedCategories')
CORE_FIELDS = frozenset(('area', 'timeWindow', 'transport'))


def configured_areas() -> list[str]:
    """Areas with a center in ``config/retrieval.json`` ``areaCenters`` (FR-020, PM 11/21).

    The list is not repeated in code. Startup (course_connection) checks every one of
    these has a center and a working radius query before support is published.
    """
    from app.retrieval.settings import CONFIG_DIR, CONFIG_FILE
    centers = json.loads((CONFIG_DIR / CONFIG_FILE).read_text(encoding='utf-8')).get('areaCenters')
    if not isinstance(centers, dict) or not centers:
        raise ValueError('retrieval.json areaCenters must list at least one area')
    unknown = set(centers) - set(get_args(Area))
    if unknown:
        raise ValueError(f'retrieval.json areaCenters has unsupported areas: {sorted(unknown)}')
    return list(centers)


@dataclass(frozen=True)
class ProfileSupport:
    # Set only in the composition root after the real #22 adapter is connected
    # and the corresponding integration checks pass. No environment switch.
    candidate_search_connected: bool = False
    verified_fields: frozenset[str] = field(default_factory=frozenset)
    mobility_verified: bool = False
    # Defaults closed for injected apps. The ordinary root enables it after
    # actual #22/consent/conditional integration checks and explicit authorization.
    unknown_accessibility_verified: bool = False

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.candidate_search_connected, self.mobility_verified,
                                                    self.unknown_accessibility_verified)):
            raise ValueError('connection evidence must be boolean')
        if not isinstance(self.verified_fields, frozenset) or not self.verified_fields <= set(INITIAL_FIELDS):
            raise ValueError('unsupported initial profile fields')


def build_profile_capabilities(support: ProfileSupport | None = None) -> Capabilities:
    support = support or ProfileSupport()
    enabled = support.candidate_search_connected and CORE_FIELDS <= support.verified_fields
    fields = [name for name in INITIAL_FIELDS if name in support.verified_fields
              and (name != 'mobility' or support.mobility_verified)] if enabled else []
    return Capabilities(supportedAreas=configured_areas() if enabled else [],
                        supportedTransports=['WALK'] if enabled else [],
                        supportedProfileFields=fields,
                        supportsUnknownAccessibilityInclusion=(enabled and support.mobility_verified
                            and 'mobility' in fields and support.unknown_accessibility_verified),
                        supportsCourseAdjustment=False, supportsWeather=False)
