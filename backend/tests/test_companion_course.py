"""Same synthetic candidates under draft weights; hard constraints stay mandatory."""
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.application.extraction import blank_profile
from app.companion_demo import create_demo
from app.courses.scheduler import default_score
from app.domain.place import OpenHoursRecord
from test_courses import CONTRACT


def ready(kind=None, *, mobility=None, infant=False):
    value = blank_profile()
    value['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
    value['timeWindow'] = {'value': {'startAt': '2026-11-17T13:00:00+09:00', 'endAt': '2026-11-17T15:15:00+09:00'},
                            'source': 'USER', 'strength': 'HARD'}
    if kind:
        value['companions'] = {'value': {'type': kind, 'count': 1 if kind == 'SOLO' else 2 if kind == 'COUPLE' else 3,
            'hasInfant': infant}, 'source': 'USER', 'strength': 'SOFT'}
    if mobility is not None:
        value['mobility'] = {'value': mobility, 'source': 'USER', 'strength': 'HARD'}
    return value


def seed(client, profile):
    sid = client.post('/api/sessions', json={}).json()['sessionId']
    saved = client.put('/api/sessions/' + sid + '/profile', json={'profile': profile, 'expectedProfileRevision': 0})
    assert saved.status_code == 200, saved.text
    return sid, saved.json()['profile']


def generate(client, sid):
    response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
    assert response.status_code == 200, response.text
    body = response.json()
    CONTRACT['check'](body, CONTRACT['schemas']['CourseResponse'])
    return body


@pytest.mark.parametrize('kind,expected', [('COUPLE', ['CAFE', 'EXHIBITION']),
    ('FAMILY', ['EXHIBITION', 'ATTRACTION']), ('FRIENDS', ['ATTRACTION', 'PARK']),
    ('SOLO', ['OTHER', 'CAFE']), ('OTHER', ['OTHER', 'CAFE']), (None, ['OTHER', 'CAFE'])])
def test_same_candidates_produce_draft_group_differences_but_baseline_stays_neutral(kind, expected):
    for proposal in (False, True):
        app = create_demo(proposal=proposal)
        with TestClient(app) as client:
            sid, saved = seed(client, ready(kind))
            body = generate(client, sid)
            assert body['status'] == 'SUCCESS'
            actual = [item['place']['category'] for item in body['course']['items']]
            assert actual == (expected if proposal else ['OTHER', 'CAFE'])
            assert body['course']['validation']['status'] == 'PASSED'
            assert app.state.sessions.check_current(sid, 1).profile == saved
            assert [s['field'] for s in body['suggestions']] == ['transport']
            assert all(item['reasonMethod'] == 'LLM' for item in body['course']['items'])


def test_candidate_order_is_irrelevant_for_equal_inputs():
    results = []
    for reverse in (False, True):
        app = create_demo(proposal=True)
        if reverse: app.state.course_service.retriever.places = tuple(reversed(app.state.course_service.retriever.places))
        with TestClient(app) as client:
            sid, _ = seed(client, ready('FAMILY'))
            results.append([i['place']['id'] for i in generate(client, sid)['course']['items']])
    assert results[0] == results[1]


@pytest.mark.parametrize('fault', ['hours', 'wheelchair-null', 'wheelchair-false', 'stroller', 'outside-radius', 'area', 'excluded', 'hard-indoor'])
def test_high_companion_weight_cannot_make_a_rejected_place_valid(fault):
    app = create_demo(proposal=True)
    service = app.state.course_service
    place = service.repository.places['synthetic:p03']  # FAMILY/EXHIBITION has a high draft score.
    profile = ready('FAMILY', mobility=['STROLLER'] if fault == 'stroller' else ['WHEELCHAIR'])
    if fault == 'hours': place = replace(place, open_hours=OpenHoursRecord(None, '[가상] 24시간 원문'))
    if fault == 'wheelchair-null': place = replace(place, accessibility=replace(place.accessibility, wheelchair=None))
    if fault == 'wheelchair-false': place = replace(place, accessibility=replace(place.accessibility, wheelchair=False))
    if fault == 'stroller': place = replace(place, accessibility=replace(place.accessibility, stroller=None))
    if fault == 'outside-radius': service.retriever.distances[place.id] = 1501
    if fault == 'area': place = replace(place, area='SEOMYEON')
    if fault == 'excluded': profile['excludedCategories'] = {'value': ['EXHIBITION'], 'source': 'USER', 'strength': 'HARD'}
    if fault == 'hard-indoor':
        app.state.capabilities.supportedProfileFields.append('indoorPreference')  # Explicit synthetic support only.
        profile['indoorPreference'] = {'value': 'INDOOR', 'source': 'USER', 'strength': 'HARD'}
        place = replace(place, indoor=False)
    service.repository.places[place.id] = place
    with TestClient(app) as client:
        sid, _ = seed(client, profile)
        body = generate(client, sid)
        assert body['status'] == 'SUCCESS'
        assert place.id not in {i['place']['id'] for i in body['course']['items']}
        assert body['course']['validation']['status'] == 'PASSED'


def test_injury_ten_minute_limit_and_extended_stay_survive_draft_scoring():
    app = create_demo(proposal=True)
    travel = app.state.course_service.travel_provider
    travel.matrix = {('synthetic:p03', 'synthetic:p04'): 11, ('synthetic:p04', 'synthetic:p03'): 11}
    with TestClient(app) as client:
        sid, _ = seed(client, ready('FAMILY', mobility=['INJURY']))
        course = generate(client, sid)['course']
        assert len(course['items']) == 2
        assert all(leg['minutes'] <= 10 for leg in course['legs'])
        assert course['items'][-1]['stayMinutes'] > 60
        assert course['validation']['routeAccessibility'] == 'UNVERIFIED'
        assert all(travel.injury_flags)


def test_family_infant_keeps_auto_stroller_hard_and_default_edit_suggestion():
    app = create_demo(proposal=True)
    with TestClient(app) as client:
        sid, saved = seed(client, ready('FAMILY', infant=True))
        body = generate(client, sid)
        assert saved['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
        assert all(i['place']['accessibility']['stroller'] is True for i in body['course']['items'])
        assert [s['field'] for s in body['suggestions']] == ['transport', 'mobility']
        assert app.state.sessions.check_current(sid, 1).profile['mobility'] == saved['mobility']


def test_hard_companions_remain_unsupported_in_api():
    app = create_demo(proposal=True)
    with TestClient(app) as client:
        value = ready('FAMILY')
        value['companions']['strength'] = 'HARD'
        sid, _ = seed(client, value)
        response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
        assert response.status_code == 422
        assert response.json()['error']['details'][0]['field'] == 'companions'


def test_discovered_longer_plan_still_precedes_companion_score():
    app = create_demo(proposal=True)
    service = app.state.course_service
    cafe = service.repository.places['synthetic:p02']
    service.repository.places[cafe.id] = replace(cafe, default_stay_min=90,
        open_hours=OpenHoursRecord({'tue': [{'open': '13:00', 'close': '15:00'}]}, '[가상] 13~15시'))
    value = ready('COUPLE')
    value['timeWindow']['value']['endAt'] = '2026-11-17T16:30:00+09:00'
    with TestClient(app) as client:
        sid, _ = seed(client, value)
        course = generate(client, sid)['course']
        assert len(course['items']) == 3
        assert cafe.id not in {i['place']['id'] for i in course['items']}


def test_baseline_demo_uses_original_scorer_even_when_proposal_file_exists():
    assert create_demo().state.course_service.scheduler.scorer is default_score
