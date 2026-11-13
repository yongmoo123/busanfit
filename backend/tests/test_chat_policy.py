"""Synthetic HTTP/state integration; run with PR #17 dependency present."""
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import pytest
from fastapi.testclient import TestClient

pytest.importorskip('app.constraints.mobility', reason='policy integration requires existing PR #17')
from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService
from app.constraints.parser import RuleBasedParser
from app.application.extraction import Analysis, AIConditionExtractor, ExtractionOutput, blank_profile
from app.main import create_app
from app.sessions.store import SessionError, SessionStore


def condition(value, strength='HARD', source='USER'):
    return {'value': value, 'source': source, 'strength': strength}


def ready():
    profile = blank_profile()
    profile['area'] = condition('HAEUNDAE')
    profile['timeWindow'] = condition({'startAt': '2026-11-12T13:00:00+09:00',
                                     'endAt': '2026-11-12T17:00:00+09:00'})
    return profile


class Scripted:
    def __init__(self, *analyses):
        self.analyses = list(analyses)
        self.calls = 0

    async def extract(self, message):
        self.calls += 1
        return deepcopy(self.analyses.pop(0))


def fallback(*replies):
    provider = FakeProvider(list(replies) or [FakeReply(fail=True)] * 100)
    return AIConditionExtractor(AIService(provider, timeout_seconds=0.01), RuleBasedParser())


@pytest.fixture
def environment():
    now = [0]
    store = SessionStore(clock=lambda: now[0],
                         wall_clock=lambda: datetime(2026, 11, 11, tzinfo=timezone.utc) + timedelta(seconds=now[0]))
    app = create_app(store, extractor=fallback())
    caps = app.state.capabilities
    caps.supportedAreas = ['HAEUNDAE']
    caps.supportedTransports = ['WALK']
    caps.supportedProfileFields = list(blank_profile())[:-1]
    with TestClient(app, raise_server_exceptions=False) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        yield app, store, now, client, sid


def chat(env, message, revision=0):
    return env[3].post('/api/chat', json={'sessionId': env[4], 'message': message,
                                        'expectedProfileRevision': revision})


def put(env, profile, revision=0):
    return env[3].put(f'/api/sessions/{env[4]}/profile',
                      json={'expectedProfileRevision': revision, 'profile': profile})


def seed(env, profile=None, pending=None, hints=None):
    return env[1].commit_profile(env[4], 0, profile=profile or ready(), history=[],
                                 pending_fields=pending or {}, companion_hints=hints or {})


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert response.headers['cache-control'] == 'no-store'


def test_fallback_both_missing_is503_and_does_not_change_state(environment):
    env = environment
    before = env[1].check_current(env[4], 0)
    env[2][0] = 100
    response = chat(env, 'private-sentinel')
    assert_error(response, 503, 'AI_UNAVAILABLE')
    after = env[1].check_current(env[4], 0)
    assert (after.profile, after.history, after.expires_at, after.pending_fields) == (
        before.profile, before.history, before.expires_at, before.pending_fields)
    assert 'private-sentinel' not in response.text


@pytest.mark.parametrize('message,field', [
    ('해운대', 'timeWindow'), ('2026-11-12 13시부터 17시까지', 'area'),
])
def test_fallback_one_field_present_is200_needs_input(environment, message, field):
    response = chat(environment, message)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'NEEDS_INPUT'
    assert response.json()['questions'][0]['field'] == field
    assert any(w['code'] == 'AI_FALLBACK' for w in response.json()['warnings'])


def test_normal_ai_missing_is200_not503(environment):
    environment[0].state.extractor = Scripted(Analysis(blank_profile()))
    result = chat(environment, '가상 메시지')
    assert result.status_code == 200 and result.json()['status'] == 'NEEDS_INPUT'
    assert result.json()['warnings'] == []


def test_existing_hard_values_survive_fallback_and_unrelated_exclusion(environment):
    profile = ready()
    profile['mobility'] = condition(['WHEELCHAIR'])
    seed(environment, profile)
    response = chat(environment, '카페는 빼 주세요', 1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['profile']['mobility'] == profile['mobility']
    assert body['profile']['timeWindow'] == profile['timeWindow']
    assert body['status'] == 'NEEDS_INPUT'
    assert body['questions'][0]['field'] == 'excludedCategories'
    state = environment[1].check_current(environment[4], 2)
    assert state.pending_fields == {'excludedCategories': 'UNCONFIRMED_CHANGE'}
    with pytest.raises(SessionError, match='PROFILE_INCOMPLETE'):
        environment[1].begin_course(environment[4], 2)


def test_fallback_existing_ready_and_no_unconfirmed_change_stays_ready(environment):
    seed(environment)
    response = chat(environment, '가상 메시지', 1)
    assert response.status_code == 200 and response.json()['status'] == 'READY'
    assert environment[1].begin_course(environment[4], 2).pending_fields == {}


def test_transport_chat_partial_acceptance_and_pending_persistence(environment):
    env = environment
    response = chat(env, '해운대, 2026-11-12 13시부터 17시까지, 자차로 이동')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['profile']['transport']['value'] is None
    assert body['profile']['area']['value'] == 'HAEUNDAE'
    assert body['status'] == 'NEEDS_INPUT'
    assert body['questions'][0]['field'] == 'transport'
    unrelated = chat(env, '가상 메시지', 1).json()
    assert unrelated['status'] == 'NEEDS_INPUT'
    assert unrelated['profile']['transport']['value'] is None
    accepted = chat(env, '도보로 이동', 2).json()
    assert accepted['status'] == 'READY'
    assert accepted['profile']['transport']['source'] == 'USER'
    assert env[1].check_current(env[4], 3).pending_fields == {}


@pytest.mark.parametrize('source', ['USER', 'DEFAULT'])
@pytest.mark.parametrize('card_edit', ['time_only', 'unchanged', 'strength_only', 'source_only'])
def test_card_echo_cannot_accept_pending_transport_but_explicit_chat_can(environment, source, card_edit):
    env = environment
    profile = ready()
    profile['transport'] = condition('WALK', 'SOFT', source)
    seed(env, profile)
    requested = chat(env, '자차로 이동', 1)
    assert requested.status_code == 200, requested.text
    assert requested.json()['status'] == 'NEEDS_INPUT'
    card = requested.json()['profile']
    if card_edit == 'time_only':
        card['timeWindow']['value']['endAt'] = '2026-11-12T18:00:00+09:00'
    elif card_edit == 'strength_only':
        card['transport'] = condition('WALK', 'HARD')
    elif card_edit == 'source_only':
        card['transport'] = condition('WALK', 'SOFT')
    saved = put(env, card, 2)
    assert saved.status_code == 200, saved.text
    assert saved.json()['status'] == 'NEEDS_INPUT'
    assert any(q['field'] == 'transport' for q in saved.json()['questions'])
    assert any(w['code'] == 'UNSUPPORTED_TRANSPORT' for w in saved.json()['warnings'])
    assert env[1].check_current(env[4], 3).pending_fields['transport'] == 'UNSUPPORTED_TRANSPORT'
    with pytest.raises(SessionError, match='PROFILE_INCOMPLETE'):
        env[1].begin_course(env[4], 3)
    accepted = chat(env, '도보로 이동할게요', 3)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'READY'
    assert accepted.json()['profile']['transport']['source'] == 'USER'
    assert not any(w['code'] == 'UNSUPPORTED_TRANSPORT' for w in accepted.json()['warnings'])
    assert env[1].check_current(env[4], 4).pending_fields == {}


def test_card_can_resolve_transport_when_a_different_supported_value_is_selected(environment):
    env = environment
    env[0].state.capabilities.supportedTransports = ['WALK', 'PUBLIC']  # synthetic support only
    profile = ready()
    profile['transport'] = condition('WALK', 'SOFT')
    seed(env, profile)
    requested = chat(env, '자차로 이동', 1).json()
    card = requested['profile']
    card['transport'] = condition('PUBLIC', 'SOFT')
    saved = put(env, card, 2)
    assert saved.status_code == 200, saved.text
    assert saved.json()['status'] == 'READY'
    assert env[1].check_current(env[4], 3).pending_fields == {}


def test_unsupported_put_preserves_profile_revision_pending_and_ttl(environment):
    before = seed(environment, pending={'budget': 'UNCONFIRMED_CHANGE'})
    profile = ready()
    profile['transport'] = condition('CAR')
    environment[2][0] = 100
    response = put(environment, profile, 1)
    assert_error(response, 422, 'UNSUPPORTED_CONSTRAINT')
    after = environment[1].check_current(environment[4], 1)
    assert (after.profile, after.pending_fields, after.history, after.expires_at) == (
        before.profile, before.pending_fields, before.history, before.expires_at)


def test_card_infant_normalization_removal_reset_and_cancellation(environment):
    env = environment
    profile = ready()
    profile['companions'] = condition({'type': 'FAMILY', 'count': 2, 'hasInfant': True}, 'SOFT')
    response = put(env, profile)
    assert response.status_code == 200, response.text
    profile = response.json()['profile']
    assert profile['mobility'] == condition(['STROLLER'], source='DEFAULT')
    profile['mobility'] = condition([])
    removed = put(env, profile, 1).json()
    assert removed['profile']['mobility']['value'] == []
    assert any(w['code'] == 'STROLLER_NOT_APPLIED' for w in removed['warnings'])
    repeated = chat(env, '아기 동반', 2).json()
    assert repeated['profile']['mobility']['value'] == []
    profile = repeated['profile']
    profile['mobility'] = condition(None, source='UNSET')
    reset = put(env, profile, 3).json()
    assert reset['profile']['mobility']['source'] == 'DEFAULT'
    profile = reset['profile']
    profile['companions']['value']['hasInfant'] = False
    cancelled = put(env, profile, 4).json()
    assert cancelled['profile']['mobility']['value'] is None
    assert cancelled['profile']['mobility']['source'] == 'UNSET'


def test_explicit_stroller_addition_preserves_other_user_restrictions(environment):
    profile = ready()
    profile['mobility'] = condition(['INJURY'])
    profile['companions'] = condition({'type': 'FAMILY', 'count': 2, 'hasInfant': True}, 'SOFT')
    seed(environment, profile)
    body = chat(environment, '유모차 사용', 1).json()
    assert body['profile']['mobility'] == condition(['INJURY', 'STROLLER'])
    assert not any(w['code'] == 'STROLLER_NOT_APPLIED' for w in body['warnings'])


def test_partial_companions_apply_stroller_without_inventing_count_or_type(environment):
    seed(environment)
    body = chat(environment, '아기 동반', 1).json()
    assert body['profile']['companions']['value'] is None
    assert body['profile']['mobility'] == condition(['STROLLER'], source='DEFAULT')
    # DEC-022: unknown count/type alone does not block course readiness.
    assert body['status'] == 'READY'
    assert body['questions'] == []


def test_questions_limit_does_not_discard_hidden_pending_or_echo_confirm_it(environment):
    profile = ready()
    for field, value in [('mobility', []), ('excludedCategories', []), ('preferenceTags', [])]:
        profile[field] = condition(value)
    seed(environment, profile, {field: 'UNCONFIRMED_CHANGE' for field in
                               ['mobility', 'excludedCategories', 'preferenceTags']})
    first = chat(environment, '가상 메시지', 1).json()
    assert len(first['questions']) == 2
    assert len(environment[1].check_current(environment[4], 2).pending_fields) == 3
    echoed = put(environment, first['profile'], 2).json()
    assert echoed['status'] == 'NEEDS_INPUT'
    assert [q['field'] for q in echoed['questions']] == ['preferenceTags']
    assert environment[1].check_current(environment[4], 3).pending_fields == {'preferenceTags': 'UNCONFIRMED_CHANGE'}


def test_timeout_warning_and_no_raw_message_in_state_or_response(environment):
    environment[0].state.extractor = fallback(FakeReply(delay_seconds=1), FakeReply(delay_seconds=1))
    response = chat(environment, '해운대 private-sentinel')
    assert response.status_code == 200
    assert any(w['message'] == '응답이 늦어 일부 조건을 확인하지 못했어요. 조건 카드에서 확인해 주세요.'
               for w in response.json()['warnings'])
    current = environment[1].check_current(environment[4], 1)
    assert current.history == []
    assert 'private-sentinel' not in response.text + str(current.profile) + str(current.companion_hints)


@pytest.mark.parametrize('bad_message', ['', ' ', 3, 'x' * 1001])
def test_invalid_chat_does_not_call_extractor(environment, bad_message):
    extractor = Scripted()
    environment[0].state.extractor = extractor
    assert_error(chat(environment, bad_message), 422, 'INVALID_REQUEST')
    assert extractor.calls == 0


def test_revision_expiry_rate_limit_take_precedence_over_ai(environment):
    env = environment
    extractor = Scripted()
    env[0].state.extractor = extractor
    assert_error(chat(env, '해운대', 1), 409, 'REVISION_CONFLICT')
    env[2][0] = 1800
    assert_error(chat(env, '해운대'), 410, 'SESSION_EXPIRED')
    assert extractor.calls == 0


def test_slow_failure_cannot_overwrite_concurrent_update_or_return503(environment):
    env = environment
    class Racing:
        async def extract(self, message):
            env[1].commit_profile(env[4], 0, profile=ready(), history=[])
            return Analysis(blank_profile(), fallback=True)
    env[0].state.extractor = Racing()
    assert_error(chat(env, '가상 메시지'), 409, 'REVISION_CONFLICT')
    assert env[1].check_current(env[4], 1).profile == ready()


def test_chat_response_matches_existing_contract(environment):
    response = chat(environment, '해운대, 2026-11-12 13시부터 17시까지')
    assert response.status_code == 200, response.text
    contract = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'contracts/validate_contract.py'))
    contract['check'](response.json(), contract['schemas']['ChatResponse'])
    assert not {'pendingFields', 'companionHints'} & response.json().keys()


def test_ai_schema_validation_retries_before_using_rules(environment):
    invalid = '{"profile": {"private-sentinel": true}}'
    environment[0].state.extractor = fallback(FakeReply(invalid), FakeReply(invalid))
    response = chat(environment, '해운대')
    assert response.status_code == 200
    assert 'private-sentinel' not in response.text


def test_valid_ai_output_uses_no_fallback(environment):
    provider = FakeProvider([FakeReply(json.dumps({'profile': ready()}))])
    environment[0].state.extractor = AIConditionExtractor(AIService(provider), RuleBasedParser())
    response = chat(environment, '가상 입력')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'READY'
    assert response.json()['warnings'] == []
    assert provider.calls == 1


@pytest.mark.parametrize('invalid', [1793923200, '1793923200', '2026-11-12T13:00:00'])
def test_ai_time_schema_does_not_accept_epoch_or_naive_strings(invalid):
    profile = ready()
    profile['timeWindow']['value']['startAt'] = invalid
    with pytest.raises(ValueError):
        ExtractionOutput.model_validate_json(json.dumps({'profile': profile}), strict=True)


def test_rate_limit_does_not_call_ai_or_replace429_with503(environment):
    env = environment
    for revision in range(20):
        assert chat(env, '해운대', revision).status_code == 200
    provider_calls = env[0].state.extractor.ai._provider.calls
    assert_error(chat(env, '가상 입력', 20), 429, 'RATE_LIMITED')
    assert env[0].state.extractor.ai._provider.calls == provider_calls


def test_expiration_during_ai_does_not_commit(environment):
    env = environment
    class Expiring:
        async def extract(self, message):
            env[2][0] = 1800
            return Analysis(ready())
    env[0].state.extractor = Expiring()
    assert_error(chat(env, '가상 입력'), 410, 'SESSION_EXPIRED')


CASES = json.loads((Path(__file__).resolve().parents[2] / 'contracts/policy-cases.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_existing_contract_policy_cases_over_http(environment, case):
    """Scripted extraction isolates policy behavior from Korean model accuracy."""
    env = environment
    before = case['before']
    env[1].commit_profile(env[4], 0, profile=before['profile'], history=[],
                          pending_fields={name: 'UNSUPPORTED_TRANSPORT' if name == 'transport'
                                          else 'UNCONFIRMED_CHANGE' for name in before['pendingFields']})
    if case['operation'] == 'put':
        response = put(env, case['request']['profile'], 1)
    else:
        # This fixture explicitly models an unresolved mobility modification.
        unconfirmed = {'mobility'} if case['id'] == 'fallback-unconfirmed-change' else set()
        env[0].state.extractor = Scripted(Analysis(case['extractedProfile'], unconfirmed,
                                                  fallback=case['fallbackUsed']))
        response = chat(env, case['request']['message'], 1)
    assert response.status_code == case['expectedHttp'], response.text
    expected, body = case['expectedResponse'], response.json()
    if response.status_code != 200:
        assert body['error']['code'] == expected['error']['code']
        assert env[1].check_current(env[4], 1).profile == before['profile']
    else:
        assert body['profile'] == expected['profile']
        assert body['status'] == expected['status']
        assert [q['field'] for q in body['questions']] == [q['field'] for q in expected['questions']]
        assert {w['code'] for w in body['warnings']} == {w['code'] for w in expected['warnings']}
        state = env[1].check_current(env[4], 2)
        unresolved = set(state.pending_fields) | {name for name in ('area', 'timeWindow')
                                                if state.profile[name]['value'] is None}
        assert unresolved == set(case['expectedPendingFields'])
