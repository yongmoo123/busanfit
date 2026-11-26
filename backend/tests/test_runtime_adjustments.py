"""Ordinary DB/travel startup and adjustment HTTP; model replies are network-free."""
from dataclasses import replace
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService
from app.application.adjustment_interpreter import AdjustmentInterpreter
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.courses.fakes import synthetic_place
from app.data.db import connect
from app.main import create_app, create_runtime_app
from test_courses import ready, CONTRACT
from test_place_repository_sqlite import insert_records
from test_server_sqlite_integration import stored


@pytest.mark.parametrize('support,expected', [
    (ProfileSupport(course_adjustment_verified=True), False),
    (ProfileSupport(True, frozenset({'area'}), True, True, True), False),
    (ProfileSupport(True, frozenset(INITIAL_FIELDS), False, True, True), False),
    (ProfileSupport(True, frozenset(INITIAL_FIELDS), True, True), False),
    (ProfileSupport(True, frozenset(INITIAL_FIELDS), True, True, True), True),
])
def test_adjustment_support_requires_connected_core_mobility_and_explicit_verification(support, expected):
    assert build_profile_capabilities(support).supportsCourseAdjustment is expected


@pytest.mark.parametrize('invalid', [1, 'true', None])
def test_adjustment_verification_is_a_strict_boolean(invalid):
    with pytest.raises(ValueError, match='boolean'):
        ProfileSupport(course_adjustment_verified=invalid)


@pytest.mark.parametrize('op,expected', [('REMOVE', 'SUCCESS'), ('REPLACE', 'SUCCESS'),
    ('EXTEND_STAY', 'SUCCESS'), ('UNCLEAR', 'NEEDS_INPUT')])
def test_runtime_activates_http_operations_with_fake_model_and_actual_adapters(stored, monkeypatch, op, expected):
    path = stored[0]
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(path))
    monkeypatch.delenv('BUSANFIT_WALK_RADIUS_M', raising=False)
    intent = {'op': op, 'targets': [2] if op != 'UNCLEAR' else []}
    if op == 'EXTEND_STAY':
        intent['minutes'] = 15
    provider = FakeProvider([FakeReply(json_text=json.dumps(intent))])
    app = create_app(connect_real_data=True,
        adjustment_interpreter=AdjustmentInterpreter(AIService(provider)))
    assert not app.state.capabilities.supportsCourseAdjustment
    with TestClient(app) as client:
        session = client.post('/api/sessions', json={}).json()
        assert session['capabilities']['supportsCourseAdjustment']
        sid = session['sessionId']
        saved = client.put(f'/api/sessions/{sid}/profile',
            json={'profile': ready(), 'expectedProfileRevision': 0}).json()
        before = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1}).json()['course']
        if op == 'REPLACE':
            candidate = synthetic_place('replacement')
            candidate = replace(candidate, source_id='1',
                accessibility=replace(candidate.accessibility, source_id='2'))
            conn = connect(path)
            try:
                insert_records(conn, [candidate], [])
            finally:
                conn.close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        response = client.post(f'/api/courses/{before["id"]}/adjust', json={
            'sessionId': sid, 'expectedProfileRevision': 1, 'message': '[가상] 수정 요청'})
        assert response.status_code == 200, response.text
        body = response.json()
        CONTRACT['check'](body, CONTRACT['schemas']['AdjustmentResponse'])
        assert body['status'] == expected and body['profileRevision'] == 1
        assert provider.calls == 1
        assert app.state.sessions.check_current(sid, 1).profile == saved['profile']
        if expected == 'SUCCESS':
            assert body['course']['id'] != before['id']
            assert body['course']['validation']['status'] == 'PASSED'
            assert client.post(f'/api/courses/{before["id"]}/adjust', json={
                'sessionId': sid, 'expectedProfileRevision': 1, 'message': '2번 빼줘'}).status_code == 409
            assert provider.calls == 1
        else:
            assert body['course'] == before and body['questions']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not app.state.capabilities.supportsCourseAdjustment
    assert app.state.course_service is None


def test_runtime_without_model_still_handles_simple_remove_only(stored, monkeypatch):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    app = create_runtime_app()
    with TestClient(app) as client:
        session = client.post('/api/sessions', json={}).json()
        assert session['capabilities']['supportsCourseAdjustment']
        sid = session['sessionId']
        client.put(f'/api/sessions/{sid}/profile', json={'profile': ready(), 'expectedProfileRevision': 0})
        original = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1}).json()['course']
        def request(course, message):
            response = client.post(f'/api/courses/{course["id"]}/adjust', json={
                'sessionId': sid, 'expectedProfileRevision': 1, 'message': message})
            assert response.status_code == 200, response.text
            return response.json()
        rejected = request(original, '2번 다른 카페로 바꿔줘')
        assert rejected['status'] == 'NEEDS_INPUT' and rejected['course'] == original
        removed = request(original, '2번 빼줘')
        assert removed['status'] == 'SUCCESS'
        assert 'AI_FALLBACK' in {w['code'] for w in removed['warnings']}
