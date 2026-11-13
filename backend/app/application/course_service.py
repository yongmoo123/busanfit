"""Retrieve -> canonical Repository facts -> schedule -> validate/repair -> wire."""
from dataclasses import dataclass

from app.api.profile_models import Profile
from app.constraints.defaults import apply_walk_default
from app.constraints.profile import ProfileError, validate_profile
from app.constraints.mobility import normalize_mobility
from app.courses.presentation import build_course, warning
from app.courses.scheduler import CourseScheduler, TravelCache
from app.courses.validator import CourseValidator, candidate_violations
from app.domain.course import CourseSettings


@dataclass(repr=False)
class CourseResult:
    course: object | None
    warnings: list
    excluded_unknown: dict
    repair_attempts: int


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
        if profile.includeUnknownAccessibility:
            raise ProfileError('UNSUPPORTED_CONSTRAINT', 'includeUnknownAccessibility', '미확인 접근성 포함 기능은 아직 지원하지 않습니다.')
        for name in ('budget', 'preferenceTags'):
            condition = getattr(profile, name)
            if condition.value is not None and condition.value != []:
                raise ProfileError('UNSUPPORTED_CONSTRAINT', name, '현재 코스 엔진에서 지원하지 않는 조건입니다.')
        if profile.transport.value != 'WALK':
            raise ProfileError('UNSUPPORTED_CONSTRAINT', 'transport', '현재 코스 엔진은 도보만 지원합니다.')
        if profile.companions.value is not None and profile.companions.strength == 'HARD':
            raise ProfileError('UNSUPPORTED_CONSTRAINT', 'companions', '동행의 하드 조건을 확인할 데이터가 없습니다.')
        result = self.retriever.retrieve(profile)
        unknown_ids = set(result.excluded_unknown_ids)
        unknown_fields = set(result.excluded_unknown_fields)
        warnings = [*default_warnings, warning('ROUTE_ACCESSIBILITY_UNVERIFIED', '장소의 접근성 정보만 확인했어요. 실제 이동 경로의 계단·경사는 확인하지 못했어요.'),
                    warning('TRAVEL_SCOPE', '첫 장소 이전과 마지막 장소 이후의 이동시간은 포함하지 않아요.'),
                    warning('PRICE_UNKNOWN', '가격 정보가 없어 전체 비용을 추정하지 않았어요.')]
        unique = {}
        for candidate in result.candidates[:self.settings.max_candidates]:
            unique.setdefault(candidate.place.id, candidate.distance_m)
        original = list(unique.items())[:self.settings.max_candidates]
        if len(result.candidates) > self.settings.max_candidates:
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
                from app.domain.place import PlaceCandidate
                candidate = PlaceCandidate(record, distance)
                violations = candidate_violations(candidate, profile, self.settings)
                if violations:
                    blocked.add(place_id)
                    for violation in violations:
                        if violation.unknown:
                            unknown_ids.add(place_id)
                            unknown_fields.update(violation.fields)
                    continue
                candidates.append(candidate)
                distances[place_id] = distance
            plan = self.scheduler.schedule(tuple(candidates), profile, travel)
            if len(plan.visits) < 2:
                break
            validation = self.validator.validate(plan, profile, distances, travel)
            if validation.passed:
                course = build_course(plan, profile, revision, self.repository, validation.checked_fields)
                # Re-read facts before handing off the fully assembled result.
                # If a source fetch raced with a place update, repair instead.
                final_check = self.validator.validate(plan, profile, distances, travel)
                if final_check.passed:
                    break
                course = None
                validation = final_check
            if attempt == self.settings.max_repair_attempts:
                break
            for violation in validation.violations:
                blocked.update(violation.place_ids)
                if violation.unknown:
                    unknown_ids.update(violation.place_ids)
                    unknown_fields.update(violation.fields)
        if blocked:
            warnings.append(warning('CANDIDATES_REJECTED', '조건을 충족하지 않거나 확인할 수 없는 후보를 제외했어요.'))
        if attempts:
            warnings.append(warning('COURSE_REPAIRED', '검증 후 일부 장소·구간을 다시 구성했어요.'))
        if travel.unavailable:
            warnings.append(warning('TRAVEL_TIME_UNAVAILABLE', '이동시간을 확인할 수 없는 구간은 사용하지 않았어요.'))
        if course is None:
            warnings.append(warning('INSUFFICIENT_PLACES', '조건을 확인한 장소를 시간 안에 두 곳 이상 배치하지 못했어요.'))
        else:
            unknown_ids -= {item.place.id for item in course.items}
        return CourseResult(course, warnings,
            {'count': len(unknown_ids), 'fields': sorted(unknown_fields) if unknown_ids else []}, attempts)
