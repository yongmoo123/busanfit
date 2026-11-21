"""FR-012 detail contract using only explicitly synthetic Repository records."""
from dataclasses import replace
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from app.courses.fakes import FakeRepository, synthetic_place, synthetic_source
from app.domain.place import OpenHoursRecord
from app.main import create_app
from test_courses import CONTRACT


@pytest.fixture
def detail():
    place = synthetic_place('detail')
    repository = FakeRepository([place])
    with TestClient(create_app(place_repository=repository), raise_server_exceptions=False) as client:
        yield client, repository, place


def fetch(detail):
    client, _, place = detail
    return client.get('/api/places/' + place.id)


def test_detail_contract_and_no_session_requirement(detail):
    response = fetch(detail)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    CONTRACT['check'](body, CONTRACT['schemas']['PlaceResponse'])
    assert body['place']['id'] == detail[2].id
    assert body['place']['price']['status'] == 'UNKNOWN'
    assert body['place']['sourceIds'] == ['synthetic-source']
    assert len(body['sources']) == 1
    assert 'reason' not in body['place']
    assert UUID(body['requestId']) != UUID(fetch(detail).json()['requestId'])
    assert any(w['code'] == 'DATA_NOTICE' for w in body['warnings'])


@pytest.mark.parametrize('text', [None, '[가상] 원문만 있고 구조화되지 않음', '24시간'])
def test_unknown_hours_keep_text_without_claiming_always_open(detail, text):
    _, repository, place = detail
    repository.places[place.id] = replace(place, open_hours=OpenHoursRecord(None, text))
    body = fetch(detail).json()
    assert body['place']['openHours'] == {'status': 'UNKNOWN', 'description': text}
    assert any(w['code'] == 'OPEN_HOURS_UNKNOWN' for w in body['warnings'])


def test_missing_accessibility_and_price_stay_unknown(detail):
    _, repository, place = detail
    repository.places[place.id] = replace(place, accessibility=None, indoor=None, price_amount=0, price_text='[가상] 무료')
    body = fetch(detail).json()
    access = body['place']['accessibility']
    assert access['grade'] == 'UNKNOWN' and access['wheelchair'] is None
    assert access['evidence'] == [] and body['place']['indoor'] is None
    assert body['place']['price']['amount'] is None
    assert body['place']['price']['status'] == 'UNKNOWN'


@pytest.mark.parametrize('wheelchair,stroller,stored_grade', [
    (False, None, 'UNSUITABLE'),
    (None, False, 'UNSUITABLE'),
    (False, False, 'UNSUITABLE'),
    (True, False, 'VERIFIED'),
    (None, None, 'UNKNOWN'),
    # An older DB may still have UNKNOWN: presentation must not infer a grade.
    (True, True, 'UNKNOWN'),
])
def test_detail_preserves_stored_grade_and_nullable_items(detail, wheelchair, stroller, stored_grade):
    _, repository, place = detail
    repository.places[place.id] = replace(place, accessibility=replace(
        place.accessibility, grade=stored_grade, wheelchair=wheelchair, stroller=stroller))
    body = fetch(detail).json()
    CONTRACT['check'](body, CONTRACT['schemas']['PlaceResponse'])
    access = body['place']['accessibility']
    assert access['grade'] == stored_grade
    assert access['wheelchair'] is wheelchair
    assert access['stroller'] is stroller


def test_multiple_sources_are_complete_ordered_and_deduplicated(detail):
    _, repository, place = detail
    source = replace(synthetic_source(), id='access-source', code='synthetic-access')
    repository.sources[source.id] = source
    repository.places[place.id] = replace(place, accessibility=replace(place.accessibility, source_id=source.id))
    body = fetch(detail).json()
    assert body['place']['sourceIds'] == ['synthetic-source', 'access-source']
    assert [s['id'] for s in body['sources']] == body['place']['sourceIds']
    assert all(e['sourceId'] == source.id for e in body['place']['accessibility']['evidence'])


@pytest.mark.parametrize('identifier', ['synthetic:absent', 'bad-id', 'synthetic:bad%3Fx', 'synthetic:' + 'x' * 65])
def test_missing_place_is_404_and_does_not_echo_path(detail, identifier):
    response = detail[0].get('/api/places/' + identifier)
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'NOT_FOUND'
    assert identifier not in response.text


@pytest.mark.parametrize('method', ['get_place', 'get_sources'])
def test_dependency_failures_are_sanitized_500_not_missing(detail, method, caplog):
    def fail(*args):
        raise RuntimeError('private-sentinel')
    setattr(detail[1], method, fail)
    response = fetch(detail)
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'INTERNAL_ERROR'
    assert 'private-sentinel' not in response.text + caplog.text


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'wrong-id'])
def test_broken_source_references_fail_instead_of_partial_success(detail, kind):
    repository = detail[1]
    source = synthetic_source()
    repository.get_sources = lambda ids: [] if kind == 'missing' else [source, source] if kind == 'duplicate' else [replace(source, id='wrong')]
    assert fetch(detail).status_code == 500


@pytest.mark.parametrize('fields', [{'address': None}, {'address': 5}, {'open_hours': OpenHoursRecord({}, None)}])
def test_invalid_storage_records_are_not_silently_repaired(detail, fields):
    detail[1].places[detail[2].id] = replace(detail[2], **fields)
    assert fetch(detail).status_code == 500


def test_missing_repository_is_500_and_normal_app_does_not_activate_fakes():
    with TestClient(create_app()) as client:
        response = client.get('/api/places/synthetic:1')
        assert response.status_code == 500
        assert client.post('/api/sessions', json={}).json()['capabilities']['supportedAreas'] == []


def test_detail_does_not_renew_or_change_session(detail):
    client = detail[0]
    session = client.post('/api/sessions', json={}).json()
    store = client.app.state.sessions
    before = store.check_current(session['sessionId'], 0)
    fetch(detail)
    after = store.check_current(session['sessionId'], 0)
    assert before == after
