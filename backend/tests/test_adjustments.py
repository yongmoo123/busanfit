"""FR-015 synthetic HTTP/engine controls. Never call a live provider."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeProvider, FakeReply
from app.ai.gemini import GeminiProvider
from app.ai.service import AIService, CourseContext, Purpose
from app.api.adjustment_models import AdjustmentIntent
from app.application.adjustment_interpreter import AdjustmentInterpreter, InterpretedAdjustment
from app.application.course_adjustment import CourseAdjustmentService
from app.api.course_models import Course
from app.api.profile_models import Profile
from app.courses.fakes import synthetic_place
from app.domain.place import OpenHoursRecord
from app.main import create_app
from test_courses import env, ready, seed, generate, CONTRACT


class ScriptedInterpreter:
    def __init__(self, **intent):
        self.intent = AdjustmentIntent(**intent)
        self.calls = 0

    async def interpret(self, *args):
        self.calls += 1
        return InterpretedAdjustment(self.intent)


@pytest.fixture
def editable(env):
    seed(env)
    generated = generate(env)
    assert generated.status_code == 200 and generated.json()['status'] == 'SUCCESS'
    env['base'] = generated.json()['course']
    # Explicit injected fixture; ordinary startup is tested separately.
    env['app'].state.capabilities.supportsCourseAdjustment = True
    env['app'].state.adjustment_interpreter = ScriptedInterpreter(op='REMOVE', targets=[2])
    return env


def adjust(env, message='2번 빼줘', course=None, revision=1):
    response = env['client'].post('/api/courses/' + (course or env['base']['id']) + '/adjust',
        json={'sessionId': env['sid'], 'expectedProfileRevision': revision, 'message': message})
    CONTRACT['check'](response.json(), CONTRACT['schemas'][
        'AdjustmentResponse' if response.status_code == 200 else 'ErrorResponse'])
    return response


def interpret(env, **intent):
    env['app'].state.adjustment_interpreter = ScriptedInterpreter(**intent)


def test_remove_keeps_others_and_profile_and_issues_new_course_id(editable):
    e = editable
    before = e['store'].check_current(e['sid'], 1)
    response = adjust(e)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'SUCCESS' and body['profileRevision'] == 1
    assert body['course']['id'] != e['base']['id']
    expected = [p for p in e['base']['items'] if p['order'] != 2]
    assert len(body['course']['items']) == len(expected)
    for original, kept in zip(expected, body['course']['items']):
        for key in ('id', 'place', 'startAt', 'endAt', 'stayMinutes', 'reason'):
            assert kept[key] == original[key]
    assert [p['order'] for p in body['course']['items']] == list(range(1, len(expected) + 1))
    assert body['changes']['removedItemIds'] == [e['base']['items'][1]['id']]
    assert e['store'].check_current(e['sid'], 1).profile == before.profile
    assert adjust(e).status_code == 409


def test_missing_target_and_missing_minutes_keep_snapshot(editable):
    for intent, field in [({'op': 'REMOVE', 'targets': [99]}, 'adjustment.target'),
                          ({'op': 'EXTEND_STAY', 'targets': [1]}, 'adjustment.minutes')]:
        interpret(editable, **intent)
        response = adjust(editable)
        assert response.status_code == 200
        assert response.json()['status'] == 'NEEDS_INPUT'
        assert response.json()['course'] == editable['base']
        assert response.json()['questions'][0]['field'] == field


def test_removal_below_two_does_not_regenerate(editable):
    interpret(editable, op='REMOVE', targets=[p['order'] for p in editable['base']['items'][:-1]])
    body = adjust(editable).json()
    assert body['status'] == 'NOT_APPLIED' and body['course'] == editable['base']


@pytest.mark.parametrize('minutes,expected', [(15, 'SUCCESS'), (1440, 'NOT_APPLIED')])
def test_extension_preserves_places_and_only_moves_later_times(editable, minutes, expected):
    interpret(editable, op='EXTEND_STAY', targets=[2], minutes=minutes)
    response = adjust(editable)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == expected
    if expected == 'NOT_APPLIED':
        assert body['course'] == editable['base'] and not any(body['changes'].values())
    else:
        old, new = editable['base']['items'], body['course']['items']
        assert [i['place']['id'] for i in new] == [i['place']['id'] for i in old]
        assert new[0] == old[0]
        assert new[1]['stayMinutes'] == old[1]['stayMinutes'] + minutes
        assert body['course']['validation']['status'] == 'PASSED'


def add_candidate(e, *, hours=None, wheelchair=True):
    candidate = synthetic_place('replacement', category='CAFE', wheelchair=wheelchair, hours=hours)
    e['repository'].places[candidate.id] = candidate
    e['retriever'].places += (candidate,)
    return candidate


def test_replace_only_changes_target_place_and_keeps_every_time(editable):
    candidate = add_candidate(editable)
    interpret(editable, op='REPLACE', targets=[2], category='CAFE')
    response = adjust(editable)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'SUCCESS'
    for old, new in zip(editable['base']['items'], body['course']['items']):
        assert (new['startAt'], new['endAt'], new['stayMinutes']) == (old['startAt'], old['endAt'], old['stayMinutes'])
        if old['order'] == 2:
            assert new['place']['id'] == candidate.id and new['id'] != old['id']
        else:
            assert new == old
    assert not body['changes']['timeChangedItemIds']


def test_replacement_does_not_shift_schedule_to_fit_closed_place(editable):
    add_candidate(editable, hours={'fri': [{'open': '22:00', 'close': '23:00'}]})
    interpret(editable, op='REPLACE', targets=[2], category='CAFE')
    body = adjust(editable).json()
    assert body['status'] == 'NOT_APPLIED' and body['course'] == editable['base']
    message = next(w['message'] for w in body['warnings'] if w['code'] == 'ADJUSTMENT_NOT_FEASIBLE')
    assert '장소 빼기' in message and '체류 늘리기' in message and '조건을 만족' in message


@pytest.mark.parametrize('previous_code', [None, 'ADJUSTMENT_NOT_SUPPORTED', 'ADJUSTMENT_FUTURE_NOTICE'])
def test_request_warnings_do_not_accumulate_across_rejection_success_and_rejection(editable, previous_code):
    e = editable
    state = e['store'].check_current(e['sid'], 1)
    course_warnings = deepcopy(state.course_metadata['warnings'])
    assert course_warnings and all(not w['code'].startswith('ADJUSTMENT_') for w in course_warnings)
    if previous_code:
        metadata = deepcopy(state.course_metadata)
        metadata['warnings'].append({'code': previous_code, 'message': '[가상] 이전 요청 안내', 'placeIds': []})
        e['store'].commit_course(e['sid'], 1, state.course_epoch,
            course=state.last_course, metadata=metadata)

    def current_warnings(body):
        retained = [w for w in body['warnings'] if not w['code'].startswith('ADJUSTMENT_')]
        assert retained == course_warnings
        assert e['store'].check_current(e['sid'], 1).course_metadata['warnings'] == body['warnings']
        return [w for w in body['warnings'] if w['code'].startswith('ADJUSTMENT_')]

    # No PARK candidate exists in this fixture. Keep the original course.
    interpret(e, op='REPLACE', targets=[2], category='PARK')
    rejected = adjust(e, '2번 다른 공원으로 바꿔줘').json()
    assert rejected['status'] == 'NOT_APPLIED' and rejected['course'] == e['base']
    first_warnings = current_warnings(rejected)
    assert len(first_warnings) == 1 and '교체' in first_warnings[0]['message']

    interpret(e, op='EXTEND_STAY', targets=[2], minutes=15)
    extended = adjust(e, '2번에 15분 더 머물래').json()
    assert extended['status'] == 'SUCCESS' and extended['course']['id'] != e['base']['id']
    assert extended['course']['items'][1]['stayMinutes'] == e['base']['items'][1]['stayMinutes'] + 15
    assert current_warnings(extended) == []

    interpret(e, op='EXTEND_STAY', targets=[2], minutes=120)
    failed = adjust(e, '2번에 120분 더 머물래', course=extended['course']['id']).json()
    assert failed['status'] == 'NOT_APPLIED' and failed['course'] == extended['course']
    last_warnings = current_warnings(failed)
    assert len(last_warnings) == 1 and last_warnings[0]['code'] == 'ADJUSTMENT_NOT_FEASIBLE'
    assert last_warnings[0]['message'] != first_warnings[0]['message']

    # Questions must also discard the previous request's failure notice.
    interpret(e, op='UNCLEAR', targets=[])
    asked = adjust(e, '다시 확인해줘', course=extended['course']['id']).json()
    assert asked['status'] == 'NEEDS_INPUT' and asked['course'] == extended['course']
    assert current_warnings(asked) == []


def test_multiple_requests_apply_first_and_ask_about_remaining(editable):
    interpret(editable, op='REMOVE', targets=[2], followUp=[{'op': 'INDOOR', 'targets': []}])
    body = adjust(editable).json()
    assert body['status'] == 'SUCCESS' and '실내' in body['questions'][0]['message']
    pending = editable['store'].check_current(editable['sid'], 1).adjustment_context
    assert pending[0]['op'] == 'INDOOR'


@pytest.mark.parametrize('op,field,action', [('PROFILE_CHANGE', 'timeWindow', 'EDIT_PROFILE'),
                                         ('INCLUDE_UNKNOWN', None, 'INCLUDE_UNKNOWN_ACCESSIBILITY')])
def test_profile_and_consent_route_out_without_mutation(editable, op, field, action):
    editable['app'].state.capabilities.supportsUnknownAccessibilityInclusion = True
    before = editable['store'].check_current(editable['sid'], 1).profile
    interpret(editable, op=op, targets=[], field=field)
    body = adjust(editable).json()
    assert body['status'] == 'NEEDS_INPUT' and body['course'] == editable['base']
    assert body['suggestions'][0]['type'] == action
    assert editable['store'].check_current(editable['sid'], 1).profile == before
    assert not before['includeUnknownAccessibility']


def test_disabled_ordinary_factory_never_calls_adjustment_interpreter(editable):
    editable['app'].state.capabilities.supportsCourseAdjustment = False
    interpreter = editable['app'].state.adjustment_interpreter
    before = editable['store'].check_current(editable['sid'], 1)
    assert adjust(editable).status_code == 422
    assert interpreter.calls == 0
    assert editable['store'].check_current(editable['sid'], 1) == before


def test_profile_update_invalidates_previous_course(editable):
    e = editable
    response = e['client'].put(f"/api/sessions/{e['sid']}/profile",
        json={'expectedProfileRevision': 1, 'profile': ready()})
    assert response.status_code == 200
    assert adjust(e).status_code == 409
    assert adjust(e, revision=2).status_code == 404


def test_dependency_failure_does_not_change_course_or_ttl(editable, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError('private-storage-sentinel')
    before = editable['store'].check_current(editable['sid'], 1)
    monkeypatch.setattr(editable['repository'], 'get_place', fail)
    response = adjust(editable)
    assert response.status_code == 500
    assert editable['store'].check_current(editable['sid'], 1) == before
    assert 'private-storage-sentinel' not in response.text + caplog.text


@pytest.mark.parametrize('change', ['profile', 'course', 'delete'])
def test_slow_interpretation_cannot_overwrite_new_state(editable, change):
    entered, release = Event(), Event()
    base_interpreter = editable['app'].state.adjustment_interpreter
    class Slow:
        async def interpret(self, *args):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.001)
            return await base_interpreter.interpret(*args)
    editable['app'].state.adjustment_interpreter = Slow()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(adjust, editable)
        try:
            assert entered.wait(5)
            if change == 'profile':
                editable['client'].put(f"/api/sessions/{editable['sid']}/profile",
                    json={'expectedProfileRevision': 1, 'profile': ready()})
            elif change == 'course':
                assert generate(editable).status_code == 200
            else:
                editable['client'].delete(f"/api/sessions/{editable['sid']}")
        finally:
            release.set()
        assert future.result(5).status_code == (410 if change == 'delete' else 409)


def test_ai_context_contains_only_bounded_course_facts_and_mobility(editable):
    captured = []
    class Provider:
        async def complete(self, request):
            captured.append(request)
            return '{"op":"REMOVE","targets":[2]}'
    ai = AIService(Provider())
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter(ai)
    response = adjust(editable, message='[가상] private-health-sentinel 2번 빼줘')
    assert response.status_code == 200 and response.json()['status'] == 'SUCCESS'
    assert captured[0].purpose == Purpose.MODIFY
    assert len(captured[0].context.adjustment_items) == len(editable['base']['items'])
    from dataclasses import asdict
    assert 'private-health-sentinel' not in json.dumps(asdict(captured[0].context))
    state = editable['store'].check_current(editable['sid'], 1)
    assert 'private-health-sentinel' not in str(state.__dict__)


def test_fallback_does_not_guess_replacement_or_missing_extension(editable):
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter()
    assert adjust(editable, '카페에서 더 오래').json()['status'] == 'NEEDS_INPUT'
    assert adjust(editable, '2번 빼줘').json()['status'] == 'SUCCESS'


def test_two_failed_attempts_then_remove_fallback(editable):
    provider = FakeProvider([FakeReply('invalid'), FakeReply('invalid')])
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter(AIService(provider))
    body = adjust(editable).json()
    assert body['status'] == 'SUCCESS' and provider.calls == 2
    assert any(w['code'] == 'AI_FALLBACK' for w in body['warnings'])


def test_modified_context_is_sent_to_gemini_only_with_modify_purpose(editable):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': '{"op":"REMOVE","targets":[2]}'}]}, 'finishReason': 'STOP'}]})
    ai = AIService(GeminiProvider('synthetic-key', 'gemini-synthetic-model', transport=httpx.MockTransport(handler)))
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter(ai)
    assert adjust(editable).json()['status'] == 'SUCCESS'
    content = json.loads(captured[0]['contents'][0]['parts'][0]['text'])
    assert content['message'] == '2번 빼줘' and content['course']['adjustment_items'][0]['order'] == 1


def test_existing_conditional_course_remains_conditional_after_edit(env):
    e = env
    profile = ready(['WHEELCHAIR'])
    profile['includeUnknownAccessibility'] = True
    e['app'].state.capabilities.supportsUnknownAccessibilityInclusion = True
    seed(e, profile)
    # Explicitly supply the separate null-only pool rather than treating every exclusion as eligible.
    from app.domain.course import RetrievalResult, PlaceCandidate
    places = [replace(p, accessibility=replace(p.accessibility, wheelchair=None, grade='UNKNOWN')) for p in e['places']]
    e['repository'].places.update({p.id: p for p in places})
    e['retriever'].retrieve = lambda profile: RetrievalResult((), frozenset(p.id for p in places),
        frozenset({'mobility.wheelchair'}), tuple(PlaceCandidate(p, 100.) for p in places))
    generated = generate(e).json()
    assert generated['course']['validation']['status'] == 'CONDITIONAL'
    e['base'] = generated['course']
    e['app'].state.capabilities.supportsCourseAdjustment = True
    interpret(e, op='REMOVE', targets=[2])
    response = adjust(e)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'SUCCESS' and body['course']['validation']['status'] == 'CONDITIONAL'
    ids = {item['place']['id'] for item in body['course']['items']}
    warning = next(w for w in body['warnings'] if w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED')
    assert set(warning['placeIds']) == ids
    assert all(item['place']['accessibility']['wheelchair'] is None for item in body['course']['items'])


def test_extension_over_closing_time_keeps_old_course(editable):
    p = editable['base']['items'][1]
    record = editable['repository'].places[p['place']['id']]
    closing = p['endAt'][11:16]
    updated = replace(record, open_hours=OpenHoursRecord({'fri': [{'open': '09:00', 'close': closing}]}, '가상'))
    editable['repository'].places[record.id] = updated
    # The saved snapshot must match current data before testing the extension itself.
    from app.places.presentation import place_payload
    state = editable['store'].check_current(editable['sid'], 1)
    base = deepcopy(editable['base'])
    base['items'][1]['place'] = place_payload(updated)
    editable['store'].commit_course(editable['sid'], 1, state.course_epoch, course=base, metadata=state.course_metadata)
    editable['base'] = base
    interpret(editable, op='EXTEND_STAY', targets=[2], minutes=15)
    body = adjust(editable).json()
    assert body['status'] == 'NOT_APPLIED' and body['course'] == base


@pytest.mark.parametrize('fault,status', [('invalid-message', 422), ('bad-json', 400), ('stale-revision', 409), ('deleted', 410)])
def test_adjustment_errors_follow_existing_envelope(editable, fault, status):
    e = editable
    url = '/api/courses/' + e['base']['id'] + '/adjust'
    if fault == 'invalid-message':
        response = adjust(e, ' ')
    elif fault == 'bad-json':
        response = e['client'].post(url, content='{', headers={'Content-Type': 'application/json'})
    elif fault == 'stale-revision':
        response = adjust(e, revision=999)
    else:
        e['client'].delete('/api/sessions/' + e['sid'])
        response = adjust(e)
    assert response.status_code == status and set(response.json()) == {'error', 'requestId'}


def test_missing_extension_minutes_are_not_invented_and_answer_is_context_bound(editable):
    interpret(editable, op='EXTEND_STAY', targets=[1])
    body = adjust(editable, '카페에 더 오래').json()
    assert body['status'] == 'NEEDS_INPUT'
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter()
    completed = adjust(editable, '15분').json()
    assert completed['status'] == 'SUCCESS'
    assert completed['course']['items'][0]['stayMinutes'] == editable['base']['items'][0]['stayMinutes'] + 15


def test_same_course_concurrent_edits_commit_only_once(editable):
    entered = 0
    both = Event()
    class Racing:
        async def interpret(self, *args):
            nonlocal entered
            entered += 1
            if entered == 2:
                both.set()
            while not both.is_set():
                await asyncio.sleep(.001)
            return InterpretedAdjustment(AdjustmentIntent(op='REMOVE', targets=[2]))
    editable['app'].state.adjustment_interpreter = Racing()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(adjust, editable) for _ in range(2)]
        try:
            assert both.wait(5)
        finally:
            both.set()
        statuses = [future.result(5).status_code for future in futures]
    assert sorted(statuses) == [200, 409]


def test_followup_keeps_original_target_after_display_orders_change(editable):
    original = editable['base']['items'][-1]
    interpret(editable, op='REMOVE', targets=[2], followUp=[{'op': 'EXTEND_STAY',
        'targets': [original['order']], 'minutes': 15}])
    first = adjust(editable).json()
    assert first['status'] == 'SUCCESS'
    editable['app'].state.adjustment_interpreter = AdjustmentInterpreter()
    second = adjust(editable, '네', course=first['course']['id']).json()
    assert second['status'] == 'SUCCESS'
    item = next(item for item in second['course']['items'] if item['id'] == original['id'])
    assert item['stayMinutes'] == original['stayMinutes'] + 15


@pytest.mark.parametrize('bad', [{'expectedProfileRevision': True}, {'message': 2},
                               {'extra': 'forbidden'}, {'sessionId': 'bad-uuid'}])
def test_invalid_adjustment_request_never_reaches_interpreter(editable, bad):
    interpreter = editable['app'].state.adjustment_interpreter
    payload = {'sessionId': editable['sid'], 'expectedProfileRevision': 1, 'message': '2번 빼줘'} | bad
    response = editable['client'].post('/api/courses/' + editable['base']['id'] + '/adjust', json=payload)
    assert response.status_code == 422 and interpreter.calls == 0


def test_adjustment_example_and_runtime_schema_validate_same_response(editable):
    from app.api.adjustment_models import AdjustmentResponse
    body = adjust(editable).json()
    AdjustmentResponse.model_validate(body)
    bad = deepcopy(body)
    bad['status'] = 'NOT_APPLIED'
    with pytest.raises(ValueError):
        AdjustmentResponse.model_validate(bad)
    bad = deepcopy(body)
    bad['status'] = 'NEEDS_INPUT'
    bad['changes'] = {'removedItemIds': [], 'replacedItems': [], 'timeChangedItemIds': []}
    with pytest.raises(ValueError):
        AdjustmentResponse.model_validate(bad)


def test_failed_first_edit_still_exposes_remaining_request(editable):
    interpret(editable, op='EXTEND_STAY', targets=[1], minutes=1440,
        followUp=[{'op': 'REMOVE', 'targets': [2]}])
    body = adjust(editable).json()
    assert body['status'] == 'NOT_APPLIED' and body['course'] == editable['base']
    assert body['questions'] and editable['store'].check_current(editable['sid'], 1).adjustment_context
