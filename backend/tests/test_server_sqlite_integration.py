"""Real PR #41 SQLite code + synthetic rows; retrieval/travel/model stay fake.

This closes a storage/worker-thread integration gap, not real Haeundae acceptance.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import runpy
import pytest
from fastapi.testclient import TestClient
from app.ai.service import AIService
from app.application.course_service import CourseService
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.application.sqlite_adapter import ConnectionPerCallRepository
from app.courses.fakes import FakeRetriever, FakeTravel, synthetic_place, synthetic_source
from app.data.db import connect, create_database
from app.data.repository import RepositoryError
from app.explanations.fakes import SyntheticExplanationProvider
from app.explanations.generator import ExplanationGenerator
from app.main import create_app
from test_courses import ready, CONTRACT
from test_place_repository_sqlite import insert_records

audit = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'evaluation/courses/audit.py'))['audit_response']


@pytest.fixture
def stored(tmp_path):
    source = replace(synthetic_source(), id='1')
    access_source = replace(source, id='2', code='synthetic-access')
    places = [replace(p, source_id='1', accessibility=replace(p.accessibility, source_id='2'))
              for p in (synthetic_place(i) for i in range(1, 5))]
    path = create_database(tmp_path / 'synthetic.sqlite3')
    conn = connect(path)
    try:
        insert_records(conn, places, [source, access_source])
    finally:
        conn.close()
    return path, places, ConnectionPerCallRepository(path)


def app_for(stored):
    _, places, repo = stored
    travel = FakeTravel()
    service = CourseService(FakeRetriever(places), travel, repo)
    return create_app(course_service=service,
        explanation_generator=ExplanationGenerator(AIService(SyntheticExplanationProvider()), repo),
        profile_support=ProfileSupport(True, frozenset(INITIAL_FIELDS), True)), travel


@pytest.mark.parametrize('mobility', [None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']])
def test_sqlite_course_explanation_detail_and_delete_end_to_end(stored, mobility):
    app, travel = app_for(stored)
    with TestClient(app, raise_server_exceptions=False) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        saved = client.put('/api/sessions/' + sid + '/profile', json={'profile': ready(mobility), 'expectedProfileRevision': 0})
        assert saved.status_code == 200
        generated = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
        assert generated.status_code == 200
        body = generated.json()
        CONTRACT['check'](body, CONTRACT['schemas']['CourseResponse'])
        result = audit(body, saved.json()['profile'], 1, stored[2], travel,
            {p.id: 100 for p in stored[1]}, allowed_reason_methods=('LLM', 'TEMPLATE'))
        assert result['hardViolations'] == result['missingPlaceIds'] == 0
        assert all(item['reasonMethod'] == 'LLM' for item in body['course']['items'])
        for item in body['course']['items']:
            detail = client.get('/api/places/' + item['place']['id'])
            assert detail.status_code == 200
            CONTRACT['check'](detail.json(), CONTRACT['schemas']['PlaceResponse'])
            assert detail.json()['place'] == item['place']
            assert [s['id'] for s in detail.json()['sources']] == ['1', '2']
        response = client.delete('/api/sessions/' + sid)
        assert response.status_code == 204 and response.content == b''
        assert client.delete('/api/sessions/' + sid).status_code == 204
        assert client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1}).status_code == 410
        assert client.post('/api/chat', json={'sessionId': sid, 'message': '[가상] 확인', 'expectedProfileRevision': 1}).status_code == 410


def test_one_connection_per_call_supports_parallel_worker_reads(stored):
    repo = stored[2]
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(repo.get_place, [stored[1][0].id] * 16))
    assert all(p.id == stored[1][0].id for p in records)
    assert len(repo.find_within_radius(35.16, 129.16, 1500, area='HAEUNDAE')) == 4
    assert repo.existing_place_ids(p.id for p in stored[1]) == frozenset(p.id for p in stored[1])


def test_missing_database_fails_without_creating_an_empty_file(tmp_path):
    path = tmp_path / 'absent.sqlite3'
    repo = ConnectionPerCallRepository(path)
    with pytest.raises(RepositoryError): repo.get_place('synthetic:1')
    assert not path.exists()


@pytest.mark.parametrize('method,args', [('get_place', (4,)), ('get_sources', ('1',)),
    ('existing_place_ids', ('synthetic:1',)), ('find_within_radius', (91, 129, 1500))])
def test_invalid_arguments_are_rejected_before_opening_database(tmp_path, method, args):
    repo = ConnectionPerCallRepository(tmp_path / 'absent.sqlite3')
    with pytest.raises(ValueError): getattr(repo, method)(*args)


def test_broken_database_is_http_500_not_missing_place_or_insufficient(stored):
    conn = connect(stored[0])
    try:
        conn.execute('DROP TABLE accessibility')
        conn.commit()
    finally:
        conn.close()
    app, _ = app_for(stored)
    with TestClient(app, raise_server_exceptions=False) as client:
        detail = client.get('/api/places/' + stored[1][0].id)
        assert detail.status_code == 500 and detail.json()['error']['code'] == 'INTERNAL_ERROR'
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        assert client.put('/api/sessions/' + sid + '/profile', json={'profile': ready(), 'expectedProfileRevision': 0}).status_code == 200
        result = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
        assert result.status_code == 500 and 'SQL' not in result.text


def test_ordinary_server_does_not_open_sqlite_or_activate_support(stored, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('ordinary server must not open a DB')
    monkeypatch.setattr('app.application.sqlite_adapter.connect', forbidden)
    with TestClient(create_app()) as client:
        assert not client.post('/api/sessions', json={}).json()['capabilities']['supportedAreas']
