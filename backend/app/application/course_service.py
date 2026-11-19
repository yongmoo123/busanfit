"""Retrieve -> canonical Repository facts -> schedule -> validate/repair -> wire."""
from dataclasses import dataclass, field

from app.api.profile_models import Profile
from app.api.course_models import Suggestion
from app.application.suggestions import build_default_suggestions, build_unknown_accessibility_suggestions
from app.constraints.defaults import apply_walk_default
from app.constraints.profile import ProfileError, validate_profile
from app.constraints.mobility import normalize_mobility
from app.courses.presentation import build_course, warning
from app.courses.scheduler import CourseScheduler, TravelCache
from app.courses.validator import CourseValidator, candidate_violations, unknown_accessibility_fields
from app.domain.course import CourseSettings
from app.domain.place import PlaceCandidate


@dataclass(repr=False)
class CourseResult:
    course: object | None
    warnings: list
    excluded_unknown: dict
    repair_attempts: int
    suggestions: list[Suggestion] = field(default_factory=list)


class CourseService:
    def __init__(self, retriever, travel_provider, repository, *,
                 settings=CourseSettings(), scheduler=None, validator=None):
        self.retriever, self.travel_provider, self.repository = retriever, travel_provider, repository
        self.settings = settings
        self.scheduler = scheduler or CourseScheduler(settings)
        self.validator = validator or CourseValidator(repository, settings)

    def generate(self, profile: Profile, revision: int, capabilities) -> CourseResult:
        values = apply_walk_default(profile.model_dump(mode='json'), capabilities, {})
        values, default_warnings = normalize_mobility(values)
        profile = Profile.model_validate(values)
        validate_profile(profile, profile.model_dump(mode='json'), capabilities)
        allow_unknown = profile.includeUnknownAccessibility and capabilities.supportsUnknownAccessibilityInclusion
        for name in ('budget', 'preferenceTags'):
            condition = getattr(profile, name)
            if condition.value is not None and condition.value != []:
                raise ProfileError('UNSUPPORTED_CONSTRAINT', name, '현재 코스 엔진에서 지원하지 않는 조건입니다.')
        if profile.transport.value != 'WALK':
            raise ProfileError('UNSUPPORTED_CONSTRAINT', 'transport', '현재 코스 엔진은 도보만 지원합니다.')
        if profile.companions.value is not None and profile.companions.strength == 'HARD':
            raise ProfileError('UNSUPPORTED_CONSTRAINT', 'companions', '동행의 하드 조건을 확인할 데이터가 없습니다.')
        result = self.retriever.retrieve(profile)
        unknown_reasons = {place_id: set(result.excluded_unknown_fields) for place_id in result.excluded_unknown_ids}
        inclusion_pool = result.unknown_accessibility_candidates[:self.settings.max_candidates]
        eligible = {}
        # IDs/counts alone cannot distinguish unknown hours from unknown access.
        # Only explicit candidates with distance evidence are considered, and
        # Repository facts are independently checked again below and at finish.
        inspection_pool = ((*result.candidates[:self.settings.max_candidates], *inclusion_pool)
                           if capabilities.supportsUnknownAccessibilityInclusion else ())
        for candidate in inspection_pool:
            record = self.repository.get_place(candidate.place.id)
            if record is None:
                unknown_reasons.pop(candidate.place.id, None)
                continue
            if record.id != candidate.place.id:
                raise ValueError('repository ID mismatch')
            failures = candidate_violations(PlaceCandidate(record, candidate.distance_m), profile, self.settings)
            if failures and all(v.unknown for v in failures):
                unknown_reasons[record.id] = {f for v in failures for f in v.fields}
            else:
                unknown_reasons.pop(record.id, None)
            if failures and all(v.code == 'ACCESSIBILITY_UNKNOWN' for v in failures):
                eligible[record.id] = candidate.distance_m
        if allow_unknown:
            for place_id in eligible:
                unknown_reasons.pop(place_id, None)
        warnings = [*default_warnings, warning('ROUTE_ACCESSIBILITY_UNVERIFIED', '장소의 접근성 정보만 확인했어요. 실제 이동 경로의 계단·경사는 확인하지 못했어요.'),
                    warning('TRAVEL_SCOPE', '첫 장소 이전과 마지막 장소 이후의 이동시간은 포함하지 않아요.'),
                    warning('PRICE_UNKNOWN', '가격 정보가 없어 전체 비용을 추정하지 않았어요.')]
        unique = {}
        pool = (*result.candidates[:self.settings.max_candidates],
                *(c for c in inclusion_pool if c.place.id in eligible)) if allow_unknown else result.candidates[:self.settings.max_candidates]
        for candidate in pool:
            unique.setdefault(candidate.place.id, candidate.distance_m)
        original = list(unique.items())[:self.settings.max_candidates]
        if len(result.candidates) > self.settings.max_candidates or len(unique) > self.settings.max_candidates:
            warnings.append(warning('CANDIDATE_LIMIT', '후보 수 상한 안에서 코스를 구성했어요.'))
        blocked = set()
        travel = TravelCache(self.travel_provider, injury='INJURY' in (profile.mobility.value or ()))
        course = None
        attempts = 0
        for attempt in range(self.settings.max_repair_attempts + 1):
            attempts = attempt
            candidates = []
            distances = {}
            for place_id, distance in original:
                if place_id in blocked:
                    continue
                record = self.repository.get_place(place_id)
                if record is None:
                    blocked.add(place_id)
                    continue
                if record.id != place_id:
                    raise ValueError('repository ID mismatch')
                candidate = PlaceCandidate(record, distance)
                violations = candidate_violations(candidate, profile, self.settings,
                                                   allow_unknown_accessibility=allow_unknown)
                if violations:
                    blocked.add(place_id)
                    if all(v.unknown for v in violations):
                        unknown_reasons[place_id] = {f for v in violations for f in v.fields}
                    else:
                        unknown_reasons.pop(place_id, None)
                    continue
                candidates.append(candidate)
                distances[place_id] = distance
            plan = self.scheduler.schedule(tuple(candidates), profile, travel)
            if len(plan.visits) < 2:
                break
            validation_options = {'allow_unknown_accessibility': True} if allow_unknown else {}
            validation = self.validator.validate(plan, profile, distances, travel, **validation_options)
            if validation.accepted:
                course = build_course(plan, profile, revision, self.repository, validation.checked_fields,
                                      unverified_fields=validation.unverified_fields)
                # Re-read facts before handing off the fully assembled result.
                # If a source fetch raced with a place update, repair instead.
                final_check = self.validator.validate(plan, profile, distances, travel, **validation_options)
                if final_check.accepted:
                    break
                course = None
                validation = final_check
            for violation in validation.violations:
                blocked.update(violation.place_ids)
            for place_id in {p for v in validation.violations for p in v.place_ids}:
                # Snapshot drift triggers repair; it is not itself evidence
                # that a place is closed or inaccessible in the current facts.
                failures = [v for v in validation.violations if place_id in v.place_ids
                            and v.code != 'PLACE_FACTS_CHANGED']
                if failures and all(v.unknown for v in failures):
                    unknown_reasons[place_id] = {f for v in failures for f in v.fields}
                else:
                    unknown_reasons.pop(place_id, None)
            if attempt == self.settings.max_repair_attempts:
                break
        if blocked:
            warnings.append(warning('CANDIDATES_REJECTED', '조건을 충족하지 않거나 확인할 수 없는 후보를 제외했어요.'))
        if attempts:
            warnings.append(warning('COURSE_REPAIRED', '검증 후 일부 장소·구간을 다시 구성했어요.'))
        if travel.unavailable:
            warnings.append(warning('TRAVEL_TIME_UNAVAILABLE', '이동시간을 확인할 수 없는 구간은 사용하지 않았어요.'))
        if course is None:
            warnings.append(warning('INSUFFICIENT_PLACES', '조건을 확인한 장소를 시간 안에 두 곳 이상 배치하지 못했어요.'))
        else:
            for item in course.items:
                unknown_reasons.pop(item.place.id, None)
            included_ids = [visit.place.id for visit in plan.visits if allow_unknown
                            and unknown_accessibility_fields(visit.place, profile)]
            if included_ids:
                warnings.append(warning('UNKNOWN_ACCESSIBILITY_INCLUDED',
                    '접근성 정보를 확인하지 못한 장소가 포함되어 있어요. 이용 가능 여부를 방문 전에 확인해 주세요.', included_ids))
        suggestions = build_default_suggestions(profile, capabilities) if course is not None else []
        # Preserve current cap/order and insufficient-response behavior until
        # the three pending UI policies are agreed. Never evict a default chip.
        if course is not None and len(suggestions) < 3:
            still_eligible = False
            if capabilities.supportsUnknownAccessibilityInclusion and not profile.includeUnknownAccessibility:
                for place_id, distance in eligible.items():
                    record = self.repository.get_place(place_id)
                    if record is None:
                        unknown_reasons.pop(place_id, None)
                        continue
                    if record.id != place_id:
                        raise ValueError('repository ID mismatch')
                    failures = candidate_violations(PlaceCandidate(record, distance), profile, self.settings)
                    if failures and all(v.code == 'ACCESSIBILITY_UNKNOWN' for v in failures):
                        still_eligible = True
                    elif failures and all(v.unknown for v in failures):
                        unknown_reasons[place_id] = {f for v in failures for f in v.fields}
                    else:
                        unknown_reasons.pop(place_id, None)
            suggestions.extend(build_unknown_accessibility_suggestions(profile, capabilities, eligible=still_eligible))
        return CourseResult(course, warnings,
            {'count': len(unknown_reasons), 'fields': sorted(set().union(*unknown_reasons.values()))}, attempts,
            suggestions)
