"""Fault injection into complete drafts, independently of HTTP serialization."""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.api.profile_models import Profile, TimeWindow
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.application.course_service import CourseService
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.courses.open_hours import covers, find_slot
from app.courses.scheduler import CourseScheduler, TravelCache
from app.courses.validator import CourseValidator
from app.domain.course import CourseSettings, Plan
from app.domain.place import OpenHoursRecord
from test_courses import ready


def prepared():
    places = [synthetic_place(i) for i in range(1, 5)]
    repository = FakeRepository(places)
    profile = Profile.model_validate(ready(['INJURY']))
    profile.transport.value, profile.transport.source = 'WALK', 'DEFAULT'
    travel = TravelCache(FakeTravel(), injury=True)
    candidates = FakeRetriever(places).retrieve(profile).candidates
    distances = {p.id: 100.0 for p in places}
    plan = CourseScheduler().schedule(candidates, profile, travel)
    return profile, plan, CourseValidator(repository), distances, travel, repository


@pytest.mark.parametrize('fault', ['outside', 'overlap', 'duration', 'duplicate', 'leg-count',
    'leg-minutes', 'bool-minutes', 'unknown-place', 'radius', 'accessibility', 'hours', 'wrong-area', 'excluded'])
def test_corrupted_draft_cannot_receive_passed(fault):
    profile, plan, validator, distances, travel, repository = prepared()
    first, second = plan.visits
    if fault == 'outside':
        first = replace(first, start_at=first.start_at - timedelta(hours=1))
    elif fault == 'overlap':
        second = replace(second, start_at=first.end_at)
    elif fault == 'duration':
        first = replace(first, stay_minutes=first.stay_minutes + 1)
    elif fault == 'duplicate':
        second = replace(second, place=first.place)
    elif fault == 'leg-count':
        plan = replace(plan, travel_minutes=())
    elif fault == 'leg-minutes':
        plan = replace(plan, travel_minutes=(0,))
    elif fault == 'bool-minutes':
        plan = replace(plan, travel_minutes=(True,))
    elif fault == 'unknown-place':
        del repository.places[first.place.id]
    elif fault == 'radius':
        distances[first.place.id] = 1500.01
    elif fault == 'accessibility':
        repository.places[first.place.id] = replace(first.place, accessibility=replace(first.place.accessibility, wheelchair=None))
    elif fault == 'hours':
        repository.places[first.place.id] = replace(first.place, open_hours=OpenHoursRecord(None, '상시 영업'))
    elif fault == 'wrong-area':
        repository.places[first.place.id] = replace(first.place, area='GWANGALLI')
    elif fault == 'excluded':
        profile.excludedCategories.value, profile.excludedCategories.source = ['CAFE'], 'USER'
    plan = replace(plan, visits=(first, second))
    assert not validator.validate(plan, profile, distances, travel).passed


def test_radius_boundary_is_inclusive():
    profile, plan, validator, distances, travel, _ = prepared()
    distances.update({v.place.id: 1500 for v in plan.visits})
    assert validator.validate(plan, profile, distances, travel).passed


def test_overnight_and_24_hour_normalized_windows():
    place = synthetic_place('overnight', hours={'thu': [{'open': '18:00', 'close': '02:00'}], 'fri': []})
    start = datetime.fromisoformat('2026-11-13T00:30:00+09:00')
    end = datetime.fromisoformat('2026-11-13T01:30:00+09:00')
    assert covers(place, start, end)[0]
    assert not covers(place, start, end + timedelta(hours=1))[0]
    all_day = synthetic_place('all-day', hours={'fri': [{'open': '00:00', 'close': '24:00'}]})
    assert covers(all_day, start, end)[0]


def test_split_hours_do_not_allow_crossing_break_but_adjacent_intervals_merge():
    start = datetime.fromisoformat('2026-11-13T11:30:00+09:00')
    end = start + timedelta(hours=1)
    place = synthetic_place('split', hours={'fri': [{'open': '09:00', 'close': '12:00'}, {'open': '13:00', 'close': '18:00'}]})
    assert not covers(place, start, end)[0]
    assert find_slot(place, start, end + timedelta(hours=2), 60)[0].hour == 13
    adjacent = replace(place, open_hours=OpenHoursRecord({'fri': [{'open': '09:00', 'close': '12:00'}, {'open': '12:00', 'close': '18:00'}]}, None))
    assert covers(adjacent, start, end)[0]


def test_subminute_profile_bounds_are_rounded_forward_without_losing_stay():
    profile, _, _, _, travel, repository = prepared()
    values = profile.model_dump(mode='json')
    values['timeWindow']['value']['startAt'] = '2026-11-13T13:00:30+09:00'
    profile = Profile.model_validate(values)
    plan = CourseScheduler().schedule(FakeRetriever(repository.places.values()).retrieve(profile).candidates, profile, travel)
    assert plan.visits[0].start_at.isoformat() == '2026-11-13T13:01:00+09:00'
    assert all(v.start_at.second == v.end_at.second == 0 for v in plan.visits)


def test_repository_facts_changing_during_source_read_are_rechecked_and_repaired():
    places = [synthetic_place(i) for i in range(1, 5)]
    repository = FakeRepository(places)
    original = repository.get_sources
    changed = False
    def sources(ids):
        nonlocal changed
        if not changed:
            changed = True
            repository.places[places[0].id] = replace(places[0], accessibility=replace(places[0].accessibility, wheelchair=None))
        return original(ids)
    repository.get_sources = sources
    profile = Profile.model_validate(ready(['WHEELCHAIR']))
    service = CourseService(FakeRetriever(places), FakeTravel(), repository)
    caps = build_profile_capabilities(ProfileSupport(True, frozenset(INITIAL_FIELDS), True))
    result = service.generate(profile, 1, caps)
    assert result.course is not None and result.repair_attempts == 1
    assert places[0].id not in [item.place.id for item in result.course.items]
    assert result.excluded_unknown['count'] == 1


def test_candidate_count_visit_count_and_travel_cache_are_bounded():
    places = [synthetic_place(i) for i in range(1, 26)]
    repository, travel = FakeRepository(places), FakeTravel()
    profile_data = ready()
    profile_data['timeWindow']['value'] = {'startAt': '2026-11-13T09:00:00+09:00', 'endAt': '2026-11-13T20:00:00+09:00'}
    caps = build_profile_capabilities(ProfileSupport(True, frozenset(INITIAL_FIELDS), True))
    result = CourseService(FakeRetriever(places), travel, repository).generate(Profile.model_validate(profile_data), 1, caps)
    assert len(result.course.items) == 6
    assert travel.calls <= 20 * 19
    assert any(w['code'] == 'CANDIDATE_LIMIT' for w in result.warnings)


def test_scheduler_accepts_a_narrower_free_window_without_implementing_anchors():
    profile, _, _, _, travel, repository = prepared()
    window = TimeWindow(startAt='2026-11-13T14:00:00+09:00', endAt='2026-11-13T17:00:00+09:00')
    plan = CourseScheduler().schedule(FakeRetriever(repository.places.values()).retrieve(profile).candidates,
                                    profile, travel, available_window=window)
    assert len(plan.visits) >= 2
    assert plan.visits[0].start_at >= window.startAt and plan.visits[-1].end_at <= window.endAt
    with pytest.raises(ValueError):
        CourseScheduler().schedule((), profile, travel,
            available_window=TimeWindow(startAt='2026-11-13T12:00:00+09:00', endAt='2026-11-13T17:00:00+09:00'))


@pytest.mark.parametrize('setting', [{'max_candidates': 21}, {'max_items': 7}, {'max_repair_attempts': 4}, {'radius_meters': float('nan')}])
def test_unbounded_or_nonfinite_settings_are_rejected(setting):
    with pytest.raises(ValueError):
        CourseSettings(**setting)
