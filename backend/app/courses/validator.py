"""Independent final hard checks against Repository facts and travel evidence."""
import math

from app.api.profile_models import Profile
from app.constraints.defaults import CONFIG
from app.courses.open_hours import covers, opening_windows
from app.data.repository import PlaceRepository
from app.domain.course import CourseSettings, Plan, ValidationResult, Violation
from app.domain.place import PlaceCandidate


def candidate_violations(candidate: PlaceCandidate, profile: Profile, settings: CourseSettings):
    place, distance = candidate.place, candidate.distance_m
    result = []
    def fail(code, field, unknown=False):
        result.append(Violation(code, (field,), (place.id,), unknown))
    if place.area != profile.area.value:
        fail('AREA_MISMATCH', 'area')
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0:
        fail('RADIUS_UNVERIFIED', 'searchRadius', True)
    elif distance > settings.radius_meters:
        fail('OUTSIDE_RADIUS', 'searchRadius')
    if place.category in (profile.excludedCategories.value or []):
        fail('EXCLUDED_CATEGORY', 'excludedCategories')
    if not place.address:
        fail('PLACE_ADDRESS_UNKNOWN', 'address', True)
    spans, known = opening_windows(place, profile.timeWindow.value.startAt, profile.timeWindow.value.endAt)
    if not spans:
        fail('OPEN_HOURS_CLOSED' if known else 'OPEN_HOURS_UNKNOWN', 'openHours', not known)
    for mode in profile.mobility.value or ():
        field = 'stroller' if mode == 'STROLLER' else 'wheelchair'
        value = getattr(place.accessibility, field, None)
        if value is not True:
            fail('ACCESSIBILITY_UNKNOWN' if value is None else 'ACCESSIBILITY_REJECTED', 'mobility.' + field, value is None)
    preference = profile.indoorPreference
    if preference.strength == 'HARD' and preference.value in ('INDOOR', 'OUTDOOR'):
        expected = preference.value == 'INDOOR'
        if place.indoor is None:
            fail('INDOOR_UNKNOWN', 'indoorPreference', True)
        elif place.indoor is not expected:
            fail('INDOOR_REJECTED', 'indoorPreference')
    return tuple(result)


class CourseValidator:
    def __init__(self, repository: PlaceRepository, settings: CourseSettings = CourseSettings()):
        self.repository, self.settings = repository, settings

    def validate(self, plan: Plan, profile: Profile, distances: dict[str, float], travel) -> ValidationResult:
        violations = []
        checked = ['placeIds', 'area', 'timeWindow', 'openHours', 'transport', 'searchRadius', 'excludedCategories']
        if profile.mobility.value:
            checked.append('mobility')
        if profile.indoorPreference.value in ('INDOOR', 'OUTDOOR') and profile.indoorPreference.strength == 'HARD':
            checked.append('indoorPreference')
        def fail(code, fields, ids=(), unknown=False):
            violations.append(Violation(code, tuple(fields), tuple(ids), unknown))
        if not 2 <= len(plan.visits) <= self.settings.max_items:
            fail('INVALID_ITEM_COUNT', ('items',))
        if len(plan.travel_minutes) != max(0, len(plan.visits) - 1):
            fail('INVALID_LEG_COUNT', ('legs',))
        if any(type(minutes) is not int or minutes < 0 for minutes in plan.travel_minutes):
            fail('INVALID_LEG_MINUTES', ('travelTime',))
        ids = [visit.place.id for visit in plan.visits]
        if len(ids) != len(set(ids)):
            fail('DUPLICATE_PLACE', ('placeIds',), ids)
        existing = self.repository.existing_place_ids(ids)
        window = profile.timeWindow.value
        for visit in plan.visits:
            place_id = visit.place.id
            record = self.repository.get_place(place_id) if place_id in existing else None
            if record is None:
                fail('PLACE_NOT_FOUND', ('placeIds',), (place_id,))
                continue
            # Facts changing during scheduling cannot be returned from a stale snapshot.
            if record != visit.place:
                fail('PLACE_FACTS_CHANGED', ('placeIds',), (place_id,))
            violations.extend(candidate_violations(PlaceCandidate(record, distances.get(place_id)), profile, self.settings))
            if visit.start_at < window.startAt or visit.end_at > window.endAt or visit.start_at >= visit.end_at:
                fail('OUTSIDE_TIME_WINDOW', ('timeWindow',), (place_id,))
            if type(visit.stay_minutes) is not int or visit.stay_minutes <= 0 or (visit.end_at - visit.start_at).total_seconds() != visit.stay_minutes * 60:
                fail('INVALID_STAY', ('stayMinutes',), (place_id,))
            covered, known = covers(record, visit.start_at, visit.end_at)
            if not covered:
                fail('OPEN_HOURS_VIOLATION', ('openHours',), (place_id,), not known)
        injury = 'INJURY' in (profile.mobility.value or ())
        for index, (origin, destination) in enumerate(zip(plan.visits, plan.visits[1:])):
            ids_pair = (origin.place.id, destination.place.id)
            estimate = travel(origin.place, destination.place)
            if estimate is None:
                fail('TRAVEL_UNVERIFIED', ('travelTime',), ids_pair, True)
                continue
            if index >= len(plan.travel_minutes) or plan.travel_minutes[index] != estimate.minutes:
                fail('TRAVEL_MISMATCH', ('travelTime',), ids_pair)
            if (destination.start_at - origin.end_at).total_seconds() < estimate.minutes * 60:
                fail('TIME_OVERLAP', ('timeWindow',), ids_pair)
            if injury and estimate.minutes > CONFIG['injury']['maxLegWalkingMinutes']:
                fail('INJURY_WALK_LIMIT', ('mobility',), ids_pair)
        if profile.transport.value != 'WALK':
            fail('UNSUPPORTED_TRANSPORT', ('transport',))
        return ValidationResult(tuple(violations), tuple(checked))
