"""COMP-06 walking travel time (FR-009, DEC-016, SRS 2.5). Owner: 이찬용.

Implements ``app.domain.course.TravelTimeProvider`` unchanged:
``estimate(origin, destination, *, injury) -> TravelEstimate | None``.

minutes = ceil(haversine_m * detourFactor / (speed_kmh * 1000 / 60))
- speed: ``config/defaults.json`` ``injury.normalWalkingKmh`` (normal) or
  ``injury.walkingKmh`` (INJURY). Not hard-coded here (DEC-016: values are settings).
- detour factor and rounding tolerance: ``config/travel.json`` (proposals, see README).
- Sprint 2 scope is WALK only; the course layer reports DISTANCE_ESTIMATE / isEstimate=true.

Never returns 0 for "could not compute":
- coordinate missing (None) -> ``None`` (unavailable; scheduler skips, validator marks
  TRAVEL_UNVERIFIED);
- invalid coordinate or same place ID -> ``ValueError`` (calculation error, must raise).
A 0-minute result only comes from two different places at the same coordinates.
No DB, HTTP or LLM calls; inputs are PlaceRecord objects already read via the Repository.
"""
from collections.abc import Mapping
import json
import math
from pathlib import Path

from app.data.geo import haversine_m
from app.domain.course import TravelEstimate
from app.domain.place import PlaceRecord

_ROOT = Path(__file__).resolve().parents[3]
DEFAULTS_PATH = _ROOT / 'config/defaults.json'
TRAVEL_PATH = _ROOT / 'config/travel.json'


def _number(value, name, *, minimum, inclusive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if value < minimum or (not inclusive and value == minimum):
        raise ValueError(f'{name} out of range')
    return float(value)


def _coordinate(place, name, limit):
    value = getattr(place, name, None)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not -limit <= value <= limit:
        raise ValueError(f'invalid {name}')
    return float(value)


class WalkingTravelTimeProvider:
    """Straight-line walking estimate. Construction validates every setting (fail fast)."""

    def __init__(self, *, normal_kmh, injury_kmh, detour_factor=1.0, rounding_tolerance=1e-9):
        self.normal_kmh = _number(normal_kmh, 'normalWalkingKmh', minimum=0)
        self.injury_kmh = _number(injury_kmh, 'walkingKmh', minimum=0)
        self.detour_factor = _number(detour_factor, 'detourFactor', minimum=1.0, inclusive=True)
        self.rounding_tolerance = _number(rounding_tolerance, 'roundingToleranceMinutes',
                                          minimum=0, inclusive=True)
        if self.rounding_tolerance >= 0.01:
            raise ValueError('roundingToleranceMinutes must only absorb float noise')

    @classmethod
    def from_config(cls, defaults: Mapping | None = None, travel: Mapping | None = None):
        if defaults is None:
            defaults = json.loads(DEFAULTS_PATH.read_text(encoding='utf-8'))
        if travel is None:
            travel = json.loads(TRAVEL_PATH.read_text(encoding='utf-8'))
        injury, walk = defaults['injury'], travel['walk']
        return cls(normal_kmh=injury['normalWalkingKmh'], injury_kmh=injury['walkingKmh'],
                   detour_factor=walk['detourFactor'],
                   rounding_tolerance=walk['roundingToleranceMinutes'])

    def distance_m(self, origin, destination):
        """Straight-line meters, or None if a coordinate is missing. Invalid values raise."""
        points = []
        for place in (origin, destination):
            lat = _coordinate(place, 'latitude', 90)
            lon = _coordinate(place, 'longitude', 180)
            if lat is None or lon is None:
                return None
            points.append((lat, lon))
        return haversine_m(*points[0], *points[1])

    def estimate(self, origin: PlaceRecord, destination: PlaceRecord, *, injury: bool) -> TravelEstimate | None:
        if type(injury) is not bool:
            raise ValueError('injury must be bool')
        if origin.id == destination.id:
            raise ValueError('travel between the same place is not a leg')
        distance = self.distance_m(origin, destination)
        if distance is None:
            return None
        meters_per_minute = (self.injury_kmh if injury else self.normal_kmh) * 1000 / 60
        minutes = distance * self.detour_factor / meters_per_minute
        rounded = math.ceil(minutes - self.rounding_tolerance) if minutes > self.rounding_tolerance else 0
        return TravelEstimate(int(rounded))


def create_travel_provider() -> WalkingTravelTimeProvider:
    """Zero-argument factory for #72 ``--travel-provider app.travel.walking:create_travel_provider``."""
    return WalkingTravelTimeProvider.from_config()
