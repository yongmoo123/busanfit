"""Course pipeline boundary; real retrieval/travel remain external dependencies."""
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Protocol, TYPE_CHECKING

from app.domain.place import PlaceCandidate, PlaceRecord

if TYPE_CHECKING:
    from app.api.profile_models import Profile

_CONFIG = json.loads((Path(__file__).resolve().parents[3] / 'config/courses.json').read_text(encoding='utf-8'))


@dataclass(frozen=True)
class CourseSettings:
    radius_meters: float = _CONFIG['radiusMeters']
    max_candidates: int = _CONFIG['maxCandidates']
    max_items: int = _CONFIG['maxItems']
    max_repair_attempts: int = _CONFIG['maxRepairAttempts']

    def __post_init__(self):
        if isinstance(self.radius_meters, bool) or not isinstance(self.radius_meters, (int, float)) or not math.isfinite(self.radius_meters) or self.radius_meters <= 0:
            raise ValueError('invalid radius')
        for value, low, high in ((self.max_candidates, 2, 20), (self.max_items, 2, 6), (self.max_repair_attempts, 0, 3)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('invalid course bound')


@dataclass(frozen=True, repr=False)
class RetrievalResult:
    candidates: tuple[PlaceCandidate, ...]
    excluded_unknown_ids: frozenset[str] = field(default_factory=frozenset)
    excluded_unknown_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if not isinstance(self.candidates, tuple) or not all(isinstance(c, PlaceCandidate) for c in self.candidates):
            raise ValueError('invalid candidates')
        for values in (self.excluded_unknown_ids, self.excluded_unknown_fields):
            if not isinstance(values, frozenset) or not all(isinstance(v, str) for v in values):
                raise ValueError('invalid exclusion information')


class CandidateRetriever(Protocol):
    def retrieve(self, profile: 'Profile') -> RetrievalResult:
        """#22 adapter: up to 20 candidates, normalized records and unique exclusions."""
        ...


@dataclass(frozen=True)
class TravelEstimate:
    minutes: int

    def __post_init__(self):
        if type(self.minutes) is not int or self.minutes < 0:
            raise ValueError('invalid travel minutes')


class TravelTimeProvider(Protocol):
    def estimate(self, origin: PlaceRecord, destination: PlaceRecord, *, injury: bool) -> TravelEstimate | None:
        """Integer minutes, or unavailable. Storage/calculation errors must raise.

        Caller supplies the INJURY flag; provider owns speed and rounding.
        Sprint 2 adapter is WALK / DISTANCE_ESTIMATE / isEstimate=true.
        """
        ...


@dataclass(frozen=True, repr=False)
class Visit:
    place: PlaceRecord
    start_at: datetime
    end_at: datetime
    stay_minutes: int


@dataclass(frozen=True, repr=False)
class Plan:
    visits: tuple[Visit, ...] = ()
    travel_minutes: tuple[int, ...] = ()


@dataclass(frozen=True)
class Violation:
    code: str
    fields: tuple[str, ...]
    place_ids: tuple[str, ...] = ()
    unknown: bool = False


@dataclass(frozen=True)
class ValidationResult:
    violations: tuple[Violation, ...]
    checked_fields: tuple[str, ...]

    @property
    def passed(self):
        return not self.violations
