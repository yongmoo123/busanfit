"""Session boundaries with synthetic data and a deterministic clock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
from threading import Event
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.sessions.store import SessionError, SessionStore
from test_app import check_error


class Clock:
    now = 0

    def monotonic(self):
        return self.now

    def utc(self):
        return datetime(2026, 11, 2, tzinfo=timezone.utc) + timedelta(seconds=self.now)


@pytest.fixture
def state():
    clock = Clock()
    return clock, SessionStore(clock=clock.monotonic, wall_clock=clock.utc)


def test_create_matches_contract_and_advertises_only_supported_features(state):
    clock, store = state
    contract = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'contracts/validate_contract.py'))
    schema = contract['spec']['paths']['/api/sessions']['post']['responses']['201']['content']['application/json']['schema']
    with TestClient(create_app(store)) as client:
        first = client.post('/api/sessions', json={})
        second = client.post('/api/sessions', json={})
        assert first.status_code == second.status_code == 201
        assert first.headers['cache-control'] == 'no-store'
        body = first.json()
        contract['check'](body, schema)
        UUID(body['sessionId'])
        assert body['sessionId'] != second.json()['sessionId']
        assert body['requestId'] != second.json()['requestId']
        assert datetime.fromisoformat(body['expiresAt']) == clock.utc() + timedelta(minutes=30)
        assert not any(body['capabilities'].values())
        assert store.begin(body['sessionId'], 0).revision == 0


@pytest.mark.parametrize('payload', [None, [], {'extra': 'private-sentinel'}])
def test_create_rejects_invalid_body(payload):
    with TestClient(create_app()) as client:
        check_error(client.post('/api/sessions', json=payload), 422, 'INVALID_REQUEST')


def test_malformed_create_and_creation_limit(state):
    clock, store = state
    with TestClient(create_app(store)) as client:
        check_error(client.post('/api/sessions', content='{', headers={'Content-Type': 'application/json'}), 400, 'INVALID_REQUEST')
        for i in range(20):
            assert client.post('/api/sessions', json={}, headers={'X-Forwarded-For': f'192.0.2.{i}'}).status_code == 201
        limited = client.post('/api/sessions', json={})
        check_error(limited, 429, 'RATE_LIMITED')
        assert limited.headers['retry-after'] == '60'
        clock.now = 60
        assert client.post('/api/sessions', json={}).status_code == 201


def test_expiry_boundary_and_unsuccessful_work_does_not_extend(state):
    clock, store = state
    session = store.create('test')
    clock.now = 1799
    store.begin(session.session_id, 0)
    clock.now = 1800
    with pytest.raises(SessionError, match='SESSION_EXPIRED') as error:
        store.begin(session.session_id, 0)
    assert error.value.status == 410
    assert not store._entries
    with pytest.raises(SessionError, match='SESSION_EXPIRED'):
        store.begin('missing', 0)


def test_atomic_update_isolation_and_stale_course_result(state):
    clock, store = state
    session = store.create('test')
    profile, history = {'area': 'HAEUNDAE'}, ['synthetic']
    clock.now = 1700
    updated = store.commit_profile(session.session_id, 0, profile=profile, history=history)
    assert updated.revision == 1
    assert updated.expires_at == clock.utc() + timedelta(minutes=30)
    profile['area'] = 'NAMPO'
    history.clear()
    updated.profile.clear()
    with pytest.raises(SessionError, match='REVISION_CONFLICT') as error:
        store.commit_profile(session.session_id, 0, profile={}, history=[])
    assert error.value.status == 409
    with pytest.raises(SessionError, match='REVISION_CONFLICT'):
        store.finish_read(session.session_id, 0)
    clock.now = 1800
    current = store.begin(session.session_id, 1)
    assert current.profile == {'area': 'HAEUNDAE'}
    assert current.history == ['synthetic']
    assert current.expires_at == updated.expires_at
    finished = store.finish_read(session.session_id, 1)
    assert finished.revision == 1
    assert finished.expires_at == clock.utc() + timedelta(minutes=30)


def test_concurrent_writers_have_exactly_one_winner(state):
    _, store = state
    session = store.create('test')

    def update(i):
        try:
            return store.commit_profile(session.session_id, 0, profile={'writer': i}, history=[]).revision
        except SessionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(update, range(8)))
    assert results.count(1) == 1
    assert results.count('REVISION_CONFLICT') == 7


def test_session_rate_window(state):
    clock, store = state
    session = store.create('test')
    for _ in range(20):
        store.begin(session.session_id, 0)
    with pytest.raises(SessionError, match='RATE_LIMITED') as error:
        store.begin(session.session_id, 0)
    assert error.value.retry_after == 60
    clock.now = 60
    assert store.begin(session.session_id, 0).revision == 0


def test_idle_cleanup_and_shutdown_clear(state):
    clock, store = state
    removed = Event()
    original = store.purge_expired

    def observed_cleanup():
        original()
        if clock.now >= 1800 and not store._entries:
            removed.set()

    store.purge_expired = observed_cleanup
    with TestClient(create_app(store, cleanup_interval=0.01)) as client:
        assert client.post('/api/sessions', json={}).status_code == 201
        clock.now = 1800
        assert removed.wait(timeout=2)
        assert client.post('/api/sessions', json={}).status_code == 201
    assert not store._entries
    assert not store._clients
