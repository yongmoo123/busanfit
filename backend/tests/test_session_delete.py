"""DEC-009 deletion with synthetic state, including in-flight operations."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.sessions.store import SessionError, SessionStore
from test_app import check_error
from test_profiles import blank


@pytest.fixture
def environment():
    now = [0]
    store = SessionStore(clock=lambda: now[0])
    with TestClient(create_app(store)) as client:
        session_id = client.post('/api/sessions', json={}).json()['sessionId']
        yield store, client, session_id, now


def assert_empty_204(response):
    assert response.status_code == 204
    assert response.content == b''
    assert response.headers['cache-control'] == 'no-store'
    assert 'content-type' not in response.headers


def test_delete_removes_profile_history_and_rate_state(environment):
    store, client, sid, _ = environment
    saved = store.commit_profile(sid, 0, profile=blank(), history=['synthetic'])
    store.begin(sid, saved.revision)
    other = store.create('other')
    assert_empty_204(client.delete(f'/api/sessions/{sid}'))
    assert sid not in store._entries
    assert other.session_id in store._entries
    check_error(client.put(f'/api/sessions/{sid}/profile', json={
        'expectedProfileRevision': saved.revision, 'profile': blank(),
    }), 410, 'SESSION_EXPIRED')
    # A deletion must not reset the shared IP creation limiter.
    assert store._clients['testclient']


def test_repeat_missing_and_expired_delete_are_204(environment):
    store, client, sid, now = environment
    for _ in range(2):
        assert_empty_204(client.delete(f'/api/sessions/{sid}'))
    assert_empty_204(client.delete(f'/api/sessions/{uuid4()}'))
    expired = store.create('expired')
    now[0] = 1800
    assert_empty_204(client.delete(f'/api/sessions/{expired.session_id}'))
    assert expired.session_id not in store._entries


def test_delete_works_even_after_session_request_limit(environment):
    store, client, sid, _ = environment
    for _ in range(20):
        store.begin(sid, 0)
    assert_empty_204(client.delete(f'/api/sessions/{sid}'))
    assert sid not in store._entries


def test_bad_uuid_is_sanitized_and_keeps_existing_state(environment):
    store, client, sid, _ = environment
    check_error(client.delete('/api/sessions/private-sentinel'), 422, 'INVALID_REQUEST')
    assert store.begin(sid, 0).revision == 0


def test_inflight_commit_cannot_recreate_deleted_session(environment):
    store, client, sid, _ = environment
    started, release = Event(), Event()

    def pending_work():
        snapshot = store.begin(sid, 0)
        started.set()
        assert release.wait(2)
        return store.commit_profile(sid, snapshot.revision, profile=blank(), history=snapshot.history)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(pending_work)
        try:
            assert started.wait(2)
            assert_empty_204(client.delete(f'/api/sessions/{sid}'))
        finally:
            release.set()
        with pytest.raises(SessionError, match='SESSION_EXPIRED'):
            pending.result(timeout=2)
    with pytest.raises(SessionError, match='SESSION_EXPIRED'):
        store.finish_read(sid, 0)
    assert sid not in store._entries


def test_parallel_delete_is_idempotent(environment):
    store, client, sid, _ = environment
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.delete(f'/api/sessions/{sid}'), range(4)))
    for result in results:
        assert_empty_204(result)
    assert sid not in store._entries


def test_documented_delete_has_no_request_body_or_204_schema(environment):
    operation = environment[1].get('/openapi.json').json()['paths']['/api/sessions/{sessionId}']['delete']
    assert 'requestBody' not in operation
    assert 'content' not in operation['responses']['204']
