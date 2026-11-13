"""FR-005/006 synthetic integration; this is not validation of #22 retrieval."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.application.extraction import blank_profile
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.constraints.defaults import resolve_stay
from app.main import create_app


@pytest.mark.parametrize('category,minutes', [('CAFE', 60), ('FOOD', 70), ('EXHIBITION', 60),
    ('ATTRACTION', 60), ('PARK', 60), ('SHOPPING', 60), ('OTHER', 60)])
def test_category_defaults_have_default_provenance(category, minutes):
    duration = resolve_stay(category)
    assert (duration.minutes, duration.source) == (minutes, 'DEFAULT')


def test_facility_duration_precedes_category_but_user_duration_is_explicit():
    assert resolve_stay('EXHIBITION', facility_minutes=95).minutes == 95
    chosen = resolve_stay('EXHIBITION', facility_minutes=95, user_minutes=40)
    assert (chosen.minutes, chosen.source) == (40, 'USER')
    assert resolve_stay('CAFE', facility_minutes=45).minutes == 45
    assert resolve_stay('OTHER', defaults={'OTHER': 80}).minutes == 80


@pytest.mark.parametrize('invalid', [0, -1, True, 60.0, '60', '약 60분'])
def test_invalid_known_duration_is_not_silently_replaced(invalid):
    with pytest.raises(ValueError):
        resolve_stay('EXHIBITION', facility_minutes=invalid)
    with pytest.raises(ValueError):
        resolve_stay('EXHIBITION', user_minutes=invalid)


def test_unknown_category_is_not_misrepresented_as_other():
    with pytest.raises(ValueError):
        resolve_stay('UNRECOGNIZED')


@pytest.mark.parametrize('support', [None, ProfileSupport(),
    ProfileSupport(verified_fields=frozenset(INITIAL_FIELDS)),
    ProfileSupport(candidate_search_connected=True, verified_fields=frozenset({'area'}))])
def test_activation_remains_closed_without_connection_and_core_verification(support):
    assert not any(build_profile_capabilities(support).model_dump().values())


def test_mobility_requires_its_own_integration_verification():
    support = ProfileSupport(candidate_search_connected=True, verified_fields=frozenset(INITIAL_FIELDS))
    caps = build_profile_capabilities(support)
    assert caps.supportedAreas == ['HAEUNDAE'] and caps.supportedTransports == ['WALK']
    assert 'mobility' not in caps.supportedProfileFields
    assert not caps.supportsUnknownAccessibilityInclusion
    assert not caps.supportsCourseAdjustment and not caps.supportsWeather


def test_unimplemented_fields_cannot_be_advertised_through_the_seam():
    with pytest.raises(ValueError):
        ProfileSupport(candidate_search_connected=True, verified_fields=frozenset({'budget', 'preferenceTags'}))


@pytest.fixture
def client():
    # Explicitly synthetic evidence, injected only here. Production passes None.
    support = ProfileSupport(candidate_search_connected=True,
        verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True)
    app = create_app(profile_support=support)
    with TestClient(app) as test_client:
        sid = test_client.post('/api/sessions', json={}).json()['sessionId']
        yield test_client, sid


def save(env, profile, revision=0):
    return env[0].put(f'/api/sessions/{env[1]}/profile',
                     json={'expectedProfileRevision': revision, 'profile': profile})


def ready():
    profile = blank_profile()
    profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
    profile['timeWindow'] = {'value': {'startAt': '2026-11-13T13:00:00+09:00',
                                     'endAt': '2026-11-13T17:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
    return profile


def test_card_applies_walk_and_preserves_unlimited_budget_and_zero_distinction(client):
    response = save(client, ready())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'READY' and body['profileRevision'] == 1
    assert body['profile']['transport'] == {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}
    assert body['profile']['budget'] == {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
    # An explicit 0 KRW budget is an active constraint, not unlimited.
    profile = body['profile']
    profile['budget'] = {'value': {'amount': 0, 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['ADMISSION']},
                         'source': 'USER', 'strength': 'HARD'}
    assert save(client, profile, 1).status_code == 422


def test_card_can_reset_transport_to_default_without_forging_default_source(client):
    profile = ready()
    profile['transport'] = {'value': 'WALK', 'source': 'USER', 'strength': 'SOFT'}
    first = save(client, profile).json()
    profile = first['profile']
    profile['transport'] = {'value': None, 'source': 'UNSET', 'strength': 'SOFT'}
    result = save(client, profile, 1).json()
    assert result['profile']['transport']['source'] == 'DEFAULT'


def test_reset_cannot_accept_an_unresolved_unsupported_mode(client):
    response = client[0].post('/api/chat', json={'sessionId': client[1], 'expectedProfileRevision': 0,
        'message': '해운대, 2026-11-13 13시부터 17시까지, 자차로 이동'})
    assert response.status_code == 200, response.text
    profile = response.json()['profile']
    assert profile['transport']['value'] is None
    result = save(client, profile, 1).json()
    assert result['status'] == 'NEEDS_INPUT'
    assert result['profile']['transport']['value'] is None
    assert any(q['field'] == 'transport' for q in result['questions'])


def test_infant_default_user_removal_reset_and_other_restrictions(client):
    profile = ready()
    profile['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': True}, 'source': 'USER', 'strength': 'SOFT'}
    first = save(client, profile).json()
    assert first['profile']['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
    profile = deepcopy(first['profile'])
    profile['mobility'] = {'value': ['INJURY'], 'source': 'USER', 'strength': 'HARD'}
    second = save(client, profile, 1).json()
    assert second['profile']['mobility']['value'] == ['INJURY']
    assert any(w['code'] == 'STROLLER_NOT_APPLIED' for w in second['warnings'])
    profile['mobility']['value'] = []
    third = save(client, profile, 2).json()
    assert third['profile']['mobility']['value'] == []
    profile['mobility'] = {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
    fourth = save(client, profile, 3).json()
    assert fourth['profile']['mobility']['source'] == 'DEFAULT'


def test_injury_cannot_be_softened_on_the_card(client):
    profile = ready()
    profile['mobility'] = {'value': ['INJURY'], 'source': 'USER', 'strength': 'SOFT'}
    response = save(client, profile)
    assert response.status_code == 422
    assert response.json()['error']['details'][0]['field'] == 'mobility'


def test_ordinary_application_does_not_activate_the_synthetic_seam():
    with TestClient(create_app()) as ordinary:
        session = ordinary.post('/api/sessions', json={}).json()
        assert not any(session['capabilities'].values())
        assert ordinary.put(f"/api/sessions/{session['sessionId']}/profile",
            json={'expectedProfileRevision': 0, 'profile': ready()}).status_code == 422
