"""#23 HTTP and adversarial hard constraints using explicit synthetic ports."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy

from fastapi.testclient import TestClient
import pytest

from app.application.course_service import CourseService
from app.application.extraction import blank_profile
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.courses.scheduler import CourseScheduler
from app.courses.validator import CourseValidator
from app.domain.course import CourseSettings, Plan, ValidationResult, Violation, Visit
from app.domain.place import OpenHoursRecord
from app.main import create_app
from app.sessions.store import SessionStore

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))


def ready(mobility=None):
    profile = blank_profile()
    profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
    profile['timeWindow'] = {'value': {'startAt': '2026-11-13T13:00:00+09:00', 'endAt': '2026-11-13T18:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
    if mobility is not None:
        profile['mobility'] = {'value': mobility, 'source': 'USER', 'strength': 'HARD'}
    return profile


@pytest.fixture
def env():
    places = [synthetic_place(index) for index in range(1, 5)]
    repository, retriever, travel = FakeRepository(places), FakeRetriever(places), FakeTravel()
    service = CourseService(retriever, travel, repository)
    now = [0]
    store = SessionStore(clock=lambda: now[0], wall_clock=lambda: datetime(2026, 11, 13, tzinfo=timezone.utc) + timedelta(seconds=now[0]))
    support = ProfileSupport(candidate_search_connected=True, verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True)
    app = create_app(store, profile_support=support, course_service=service)
    with TestClient(app, raise_server_exceptions=False) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        yield {'app': app, 'client': client, 'sid': sid, 'store': store, 'now': now,
               'repository': repository, 'retriever': retriever, 'travel': travel, 'service': service, 'places': places}


def seed(env, profile=None):
    response = env['client'].put(f"/api/sessions/{env['sid']}/profile",
        json={'expectedProfileRevision': 0, 'profile': profile or ready()})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'READY'
    return response.json()


def generate(env, revision=1):
    return env['client'].post('/api/courses', json={'sessionId': env['sid'], 'profileRevision': revision})


def check_contract(response):
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    CONTRACT['check'](response.json(), CONTRACT['schemas']['CourseResponse'])


@pytest.mark.parametrize('mobility', [None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']])
def test_four_scenarios_have_only_verified_places_and_keep_profile_revision(env, mobility):
    before = seed(env, ready(mobility))
    env['now'][0] = 60
    response = generate(env)
    check_contract(response)
    result = response.json()
    assert result['status'] == 'SUCCESS'
    course = result['course']
    assert 2 <= len(course['items']) <= 6
    assert course['profileRevision'] == 1
    assert all(item['place']['id'] in env['repository'].places for item in course['items'])
    assert all(item['reasonMethod'] == 'TEMPLATE' and not item['isAnchor'] for item in course['items'])
    assert len(course['legs']) == len(course['items']) - 1
    for item in course['items']:
        for mode in mobility or []:
            field = 'stroller' if mode == 'STROLLER' else 'wheelchair'
            assert item['place']['accessibility'][field] is True
    if mobility == ['INJURY']:
        assert len(course['items']) == 2
        assert all(leg['minutes'] <= 10 for leg in course['legs'])
        assert all(env['travel'].injury_flags)
    summary = course['summary']
    assert summary['totalMinutes'] == summary['totalStayMinutes'] + summary['totalTravelMinutes'] + summary['totalWaitingMinutes']
    assert summary['estimatedCost'] == {'status': 'UNKNOWN', 'amount': None, 'currency': 'KRW', 'basis': 'UNKNOWN'}
    assert course['validation']['status'] == 'PASSED'
    assert course['validation']['routeAccessibility'] == 'UNVERIFIED'
    assert set(course['validation']['unverifiedFields']).isdisjoint(course['validation']['checkedHardConstraints'])
    state = env['store'].check_current(env['sid'], 1)
    assert state.profile == before['profile']
    assert result['sessionExpiresAt'] != before['sessionExpiresAt']


def test_unknown_accessibility_is_excluded_by_item_not_grade(env):
    seed(env, ready(['WHEELCHAIR']))
    p1, p2 = env['places'][:2]
    env['repository'].places[p1.id] = replace(p1, accessibility=replace(p1.accessibility, wheelchair=None, stroller=True, grade='VERIFIED'))
    env['repository'].places[p2.id] = replace(p2, accessibility=replace(p2.accessibility, wheelchair=False, grade='VERIFIED'))
    response = generate(env)
    check_contract(response)
    body = response.json()
    assert body['status'] == 'SUCCESS' and len(body['course']['items']) == 2
    assert body['excludedUnknown'] == {'count': 1, 'fields': ['mobility.wheelchair']}


def test_unknown_exclusions_are_unique_across_retriever_and_validator(env):
    seed(env, ready(['STROLLER']))
    p = env['places'][0]
    env['repository'].places[p.id] = replace(p, accessibility=replace(p.accessibility, stroller=None))
    env['retriever'].unknown_ids = frozenset({p.id})
    env['retriever'].unknown_fields = frozenset({'mobility.stroller'})
    assert generate(env).json()['excludedUnknown']['count'] == 1


@pytest.mark.parametrize('kind', ['unknown', 'closed', 'display-only'])
def test_missing_or_unparsed_hours_cannot_pass_as_always_open(env, kind):
    seed(env)
    for p in env['places'][:3]:
        hours = OpenHoursRecord(None, '24시간' if kind == 'display-only' else None) if kind != 'closed' else OpenHoursRecord({'fri': []}, '휴무')
        env['repository'].places[p.id] = replace(p, open_hours=hours)
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'
    assert response.json()['course'] is None
    assert response.json()['excludedUnknown']['count'] == (0 if kind == 'closed' else 3)


def test_time_window_waiting_and_opening_breaks(env):
    env['retriever'].places = tuple(env['places'][:2])
    p1, p2 = env['places'][:2]
    env['repository'].places[p1.id] = replace(p1, open_hours=OpenHoursRecord({'fri': [{'open': '13:00', 'close': '14:00'}]}, '가상'))
    env['repository'].places[p2.id] = replace(p2, open_hours=OpenHoursRecord({'fri': [{'open': '15:00', 'close': '17:00'}]}, '가상'))
    seed(env)
    response = generate(env)
    check_contract(response)
    course = response.json()['course']
    assert course['summary']['totalWaitingMinutes'] == 55
    assert course['summary']['totalMinutes'] == 180
    assert course['endAt'] == '2026-11-13T16:00:00+09:00'


@pytest.mark.parametrize('minutes,success', [(10, True), (11, False), (None, False)])
def test_injury_leg_limit_boundary_and_unknown_travel(env, minutes, success):
    env['travel'].minutes = minutes
    seed(env, ready(['INJURY']))
    response = generate(env)
    check_contract(response)
    assert (response.json()['status'] == 'SUCCESS') is success
    if minutes is None:
        assert any(w['code'] == 'TRAVEL_TIME_UNAVAILABLE' for w in response.json()['warnings'])


def test_missing_repository_place_is_not_in_output(env):
    seed(env)
    for p in env['places'][:3]:
        del env['repository'].places[p.id]
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'


@pytest.mark.parametrize('dependency', ['retrieval', 'travel', 'repository', 'sources'])
def test_dependency_errors_are_500_not_empty_results_and_do_not_leak_or_renew_ttl(env, dependency, caplog):
    before = seed(env)
    env['now'][0] = 60
    def crash(*args, **kwargs):
        raise RuntimeError('private-sentinel')
    if dependency == 'retrieval':
        env['retriever'].retrieve = crash
    elif dependency == 'travel':
        env['travel'].estimate = crash
    elif dependency == 'repository':
        env['repository'].get_place = crash
    else:
        env['repository'].get_sources = crash
    response = generate(env)
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'INTERNAL_ERROR'
    assert 'private-sentinel' not in response.text + caplog.text
    assert env['store'].check_current(env['sid'], 1).expires_at.isoformat() == datetime.fromisoformat(before['sessionExpiresAt']).isoformat()


@pytest.mark.parametrize('revision', [0, 2, True, 1.0, '1', -1])
def test_invalid_or_stale_revision_does_not_call_dependencies(env, revision):
    seed(env)
    response = generate(env, revision)
    assert response.status_code == (409 if revision == 2 else 422)
    assert env['retriever'].calls == 0


def test_malformed_request_and_chat_revision_field_are_rejected(env):
    response = env['client'].post('/api/courses', content='{', headers={'Content-Type': 'application/json'})
    assert response.status_code == 400
    response = env['client'].post('/api/courses', json={'sessionId': env['sid'], 'expectedProfileRevision': 1})
    assert response.status_code == 422 and env['retriever'].calls == 0


def test_pending_or_missing_profile_blocks_course_before_retrieval(env):
    assert generate(env, 0).status_code == 422
    seed(env)
    current = env['store'].check_current(env['sid'], 1)
    env['store'].commit_profile(env['sid'], 1, profile=current.profile, history=[], pending_fields={'mobility': 'UNCONFIRMED_CHANGE'})
    response = generate(env, 2)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'PROFILE_INCOMPLETE'
    assert env['retriever'].calls == 0


@pytest.mark.parametrize('race', ['revision', 'expiry'])
@pytest.mark.parametrize('fails', [False, True])
def test_slow_result_or_error_cannot_override_newer_session_state(env, race, fails):
    seed(env)
    retrieve = env['retriever'].retrieve
    def racing(profile):
        if race == 'revision':
            current = env['store'].check_current(env['sid'], 1)
            env['store'].commit_profile(env['sid'], 1, profile=current.profile, history=[])
        else:
            env['now'][0] = 1800
        if fails:
            raise RuntimeError('private-sentinel')
        return retrieve(profile)
    env['retriever'].retrieve = racing
    response = generate(env)
    assert response.status_code == (409 if race == 'revision' else 410)
    assert 'private-sentinel' not in response.text


def test_rate_limit_takes_precedence_over_generating_another_course(env):
    seed(env)
    for _ in range(19):
        assert generate(env).status_code == 200
    calls = env['retriever'].calls
    response = generate(env)
    assert response.status_code == 429 and response.headers['Retry-After']
    assert env['retriever'].calls == calls


def test_repair_replaces_invalid_visits_and_is_bounded(env):
    seed(env)
    original = env['service'].validator
    class RejectFirst:
        calls = 0
        def validate(self, plan, profile, distances, travel):
            self.calls += 1
            if self.calls == 1:
                return ValidationResult((Violation('TEST_REJECT', ('openHours',), (plan.visits[0].place.id,)),), ())
            return original.validate(plan, profile, distances, travel)
    validator = RejectFirst()
    env['service'].validator = validator
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'SUCCESS'
    assert any(w['code'] == 'COURSE_REPAIRED' for w in response.json()['warnings'])
    assert validator.calls == 3  # rejection, repaired plan, final fact check


def test_global_validation_failure_is_never_passed_and_retries_only_three_times(env):
    seed(env)
    class NeverPass:
        calls = 0
        def validate(self, *args):
            self.calls += 1
            return ValidationResult((Violation('TEST_REJECT', ('timeWindow',)),), ())
    validator = NeverPass()
    env['service'].validator = validator
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'
    assert validator.calls == 4  # initial + 3 repairs


def test_ordinary_server_does_not_use_synthetic_ports():
    with TestClient(create_app()) as client:
        session = client.post('/api/sessions', json={}).json()
        assert not any(session['capabilities'].values())
        response = client.post('/api/courses', json={'sessionId': session['sessionId'], 'profileRevision': 1})
        assert response.status_code == 409


def test_legacy_infant_profile_does_not_bypass_stroller_default(env):
    profile = ready()
    profile['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': True}, 'source': 'USER', 'strength': 'SOFT'}
    env['store'].commit_profile(env['sid'], 0, profile=profile, history=[])
    for p in env['places'][:3]:
        env['repository'].places[p.id] = replace(p, accessibility=replace(p.accessibility, stroller=None))
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'
    assert response.json()['excludedUnknown']['count'] == 3


@pytest.mark.parametrize('field', ['budget', 'preferenceTags', 'companions', 'includeUnknownAccessibility'])
def test_unsupported_active_constraints_do_not_get_ignored_to_make_a_course(env, field):
    seed(env)
    state = env['store'].check_current(env['sid'], 1)
    profile = state.profile
    if field == 'includeUnknownAccessibility':
        profile[field] = True
        env['app'].state.capabilities.supportsUnknownAccessibilityInclusion = True
    else:
        values = {'budget': {'amount': 0, 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['FOOD']},
                  'preferenceTags': ['가상 선호'], 'companions': {'type': 'FRIENDS', 'count': 2, 'hasInfant': False}}
        profile[field] = {'value': values[field], 'source': 'USER', 'strength': 'HARD'}
        if field not in env['app'].state.capabilities.supportedProfileFields:
            env['app'].state.capabilities.supportedProfileFields.append(field)
    env['store'].commit_profile(env['sid'], 1, profile=profile, history=[])
    response = generate(env, 2)
    assert response.status_code == 422
    assert response.json()['error']['details'][0]['field'] == field
    assert env['retriever'].calls == 0


def test_hard_indoor_preference_is_rechecked_even_if_retrieval_returns_outdoor(env):
    profile = ready()
    profile['indoorPreference'] = {'value': 'INDOOR', 'source': 'USER', 'strength': 'HARD'}
    env['app'].state.capabilities.supportedProfileFields.append('indoorPreference')  # synthetic only
    seed(env, profile)
    for p in env['places'][:3]:
        env['repository'].places[p.id] = replace(p, indoor=None if p.id == env['places'][0].id else False)
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'
    assert response.json()['excludedUnknown']['count'] == 1


def test_missing_source_is_an_error_and_never_a_fabricated_reference(env):
    seed(env)
    env['repository'].sources.clear()
    response = generate(env)
    assert response.status_code == 500 and response.json()['error']['code'] == 'INTERNAL_ERROR'


def test_subminute_profile_is_accepted_and_summary_remains_exact(env):
    profile = ready()
    profile['timeWindow']['value']['startAt'] = '2026-11-13T13:00:30+09:00'
    seed(env, profile)
    response = generate(env)
    check_contract(response)
    assert response.json()['course']['startAt'] == '2026-11-13T13:01:00+09:00'


def test_candidate_injected_facts_are_not_used_in_place_of_repository_facts(env):
    seed(env, ready(['WHEELCHAIR']))
    for p in env['places'][:3]:
        env['repository'].places[p.id] = replace(p, accessibility=replace(p.accessibility, wheelchair=False))
    # Retriever still has old True values; authoritative storage wins.
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'


def test_real_engine_is_required_instead_of_returning_fake_success(env):
    seed(env)
    env['app'].state.course_service = None
    response = generate(env)
    assert response.status_code == 500 and env['retriever'].calls == 0
