"""Synthetic profiles; enabled capabilities below are test-only, not real support."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.sessions.store import SessionStore


def blank():
    fields = ['area', 'timeWindow', 'transport', 'mobility', 'budget', 'indoorPreference', 'companions', 'excludedCategories', 'preferenceTags']
    return {**{name: {'value': None, 'source': 'UNSET', 'strength': 'HARD'} for name in fields}, 'includeUnknownAccessibility': False}


def condition(value, strength='HARD'):
    return {'value': value, 'source': 'USER', 'strength': strength}


def ready():
    profile = blank()
    profile['area'] = condition('HAEUNDAE')
    profile['timeWindow'] = condition({'startAt': '2026-11-06T13:00:00+09:00', 'endAt': '2026-11-06T17:00:00+09:00'})
    return profile


@pytest.fixture
def environment():
    now = [0]
    store = SessionStore(clock=lambda: now[0], wall_clock=lambda: datetime(2026, 11, 2, tzinfo=timezone.utc) + timedelta(seconds=now[0]))
    app = create_app(store)
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        yield app, store, now, client, sid


def put(env, profile, revision=0, sid=None):
    return env[3].put(f'/api/sessions/{sid or env[4]}/profile', json={'expectedProfileRevision': revision, 'profile': profile})


def enable_test_capabilities(env):
    caps = env[0].state.capabilities
    caps.supportedAreas = ['HAEUNDAE']
    caps.supportedTransports = ['WALK']
    caps.supportedProfileFields = list(blank().keys())[:-1]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['error']['code'] == code
    assert response.headers['cache-control'] == 'no-store'
    assert 'private-sentinel' not in response.text


def test_blank_profile_contract_revision_and_expiry(environment):
    env = environment
    env[2][0] = 100
    response = put(env, blank())
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'NEEDS_INPUT'
    assert len(body['questions']) == 2
    assert body['profileRevision'] == 1
    assert body['profile'] == blank()
    assert response.headers['cache-control'] == 'no-store'
    assert datetime.fromisoformat(body['sessionExpiresAt']) == datetime(2026, 11, 2, tzinfo=timezone.utc) + timedelta(seconds=1900)
    contract = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'contracts/validate_contract.py'))
    contract['check'](body, contract['schemas']['ProfileResponse'])


def test_swagger_example_is_executable(environment):
    client = environment[3]
    schema = client.get('/openapi.json').json()['components']['schemas']['ProfileUpdateRequest']
    response = client.put(f'/api/sessions/{environment[4]}/profile', json=schema['examples'][0])
    assert response.status_code == 200
    assert response.json()['status'] == 'NEEDS_INPUT'


def test_ready_replace_and_clear_preserve_history(environment):
    env = environment
    enable_test_capabilities(env)
    env[1].commit_profile(env[4], 0, profile=blank(), history=['synthetic'])
    first = put(env, ready(), 1)
    assert first.status_code == 200
    assert first.json()['status'] == 'READY'
    assert first.json()['questions'] == []
    second = put(env, blank(), 2)
    assert second.status_code == 200
    assert second.json()['profile']['area']['value'] is None
    assert env[1].begin(env[4], 3).history == ['synthetic']
    assert first.json()['requestId'] != second.json()['requestId']


@pytest.mark.parametrize('strength', ['HARD', 'SOFT'])
def test_unsupported_is_not_saved_or_relaxed(environment, strength):
    env = environment
    initial = put(env, blank()).json()
    profile = blank()
    profile['preferenceTags'] = condition(['private-sentinel'], strength)
    env[2][0] = 100
    response = put(env, profile, 1)
    assert_error(response, 422, 'UNSUPPORTED_CONSTRAINT')
    assert response.json()['error']['details'][0]['field'] == 'preferenceTags'
    current = env[1].begin(env[4], 1)
    assert current.profile == blank()
    assert current.expires_at == datetime.fromisoformat(initial['sessionExpiresAt'])


@pytest.mark.parametrize('field,value', [
    ('area', condition('NAMPO')),
    ('transport', condition('CAR')),
    ('includeUnknownAccessibility', True),
])
def test_unsupported_area_transport_unknown(environment, field, value):
    enable_test_capabilities(environment)
    profile = blank()
    profile[field] = value
    assert_error(put(environment, profile), 422, 'UNSUPPORTED_CONSTRAINT')


@pytest.mark.parametrize('field,value', [
    ('area', {'value': None, 'source': 'USER', 'strength': 'HARD'}),
    ('area', {'value': 'HAEUNDAE', 'source': 'UNSET', 'strength': 'HARD'}),
    ('area', condition(None, 'SOFT')),
    ('transport', {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}),
    ('mobility', condition(['INJURY', 'INJURY'])),
    ('budget', condition({'amount': 0, 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['FOOD', 'FOOD']})),
])
def test_semantic_failures_leave_revision_zero(environment, field, value):
    enable_test_capabilities(environment)
    profile = blank()
    profile[field] = value
    assert_error(put(environment, profile), 422, 'INVALID_PROFILE')
    assert environment[1].begin(environment[4], 0).profile is None


@pytest.mark.parametrize('start,end', [
    ('2026-11-06T17:00:00+09:00', '2026-11-06T13:00:00+09:00'),
    ('2026-11-06T13:00:00+09:00', '2026-11-06T13:00:00+09:00'),
    ('2026-11-06T23:00:00+09:00', '2026-11-07T01:00:00+09:00'),
    ('2026-11-06T14:00:00Z', '2026-11-06T16:00:00Z'),
])
def test_invalid_time_windows(environment, start, end):
    profile = blank()
    profile['timeWindow'] = condition({'startAt': start, 'endAt': end})
    assert_error(put(environment, profile), 422, 'INVALID_PROFILE')


@pytest.mark.parametrize('start', ['2026-11-06T13:00:00', 1793923200, '1793923200'])
def test_time_requires_offset_string(environment, start):
    profile = ready()
    profile['timeWindow']['value']['startAt'] = start
    assert_error(put(environment, profile), 422, 'INVALID_REQUEST')


@pytest.mark.parametrize('revision', [True, '0', 0.0, -1])
def test_strict_revision(environment, revision):
    assert_error(put(environment, blank(), revision), 422, 'INVALID_REQUEST')


def test_missing_extra_fields_and_wrong_types(environment):
    for mutate in [
        lambda p: p.pop('budget'),
        lambda p: p.update(extra='private-sentinel'),
        lambda p: p.update(includeUnknownAccessibility='false'),
        lambda p: p.update(companions=condition({'type': 'FAMILY', 'count': True, 'hasInfant': False})),
        lambda p: p.update(budget=condition({'amount': '0', 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['FOOD']})),
    ]:
        profile = blank()
        mutate(profile)
        assert_error(put(environment, profile), 422, 'INVALID_REQUEST')


def test_empty_list_differs_from_null_and_infant_does_not_infer_mobility(environment):
    enable_test_capabilities(environment)
    profile = blank()
    profile['mobility'] = condition([])
    profile['companions'] = condition({'type': 'FAMILY', 'count': 2, 'hasInfant': True})
    response = put(environment, profile)
    assert response.status_code == 200
    assert response.json()['profile']['mobility'] == condition([])


def test_existing_default_can_be_preserved_but_not_forged(environment):
    env = environment
    enable_test_capabilities(env)
    profile = blank()
    profile['transport'] = {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}
    env[1].commit_profile(env[4], 0, profile=profile, history=[])
    assert put(env, profile, 1).status_code == 200
    changed = deepcopy(profile)
    changed['transport']['strength'] = 'HARD'
    assert_error(put(env, changed, 2), 422, 'INVALID_PROFILE')


def test_conflict_expiry_and_rate_limit(environment):
    env = environment
    assert put(env, blank()).status_code == 200
    assert_error(put(env, blank()), 409, 'REVISION_CONFLICT')
    assert_error(put(env, blank(), sid=str(uuid4())), 410, 'SESSION_EXPIRED')
    for revision in range(1, 20):
        assert put(env, blank(), revision).status_code == 200
    limited = put(env, blank(), 20)
    assert_error(limited, 429, 'RATE_LIMITED')
    assert limited.headers['retry-after'] == '60'
    env[2][0] = 1800
    assert_error(put(env, blank(), 20), 410, 'SESSION_EXPIRED')


def test_concurrent_http_updates_only_commit_once(environment):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: put(environment, blank()), range(4)))
    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409]


def test_malformed_json_and_bad_uuid(environment):
    client = environment[3]
    response = client.put(f'/api/sessions/{environment[4]}/profile', content='{', headers={'Content-Type': 'application/json'})
    assert_error(response, 400, 'INVALID_REQUEST')
    assert_error(put(environment, blank(), sid='private-sentinel'), 422, 'INVALID_REQUEST')
