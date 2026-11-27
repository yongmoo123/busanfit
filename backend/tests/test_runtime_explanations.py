"""#96: production composition, actual DB adapters, network-free model boundary."""
from contextlib import asynccontextmanager
import json

from fastapi.testclient import TestClient
import pytest

from app.ai.service import AIService, Purpose
from app.application.extraction import AIConditionExtractor
from app.constraints.chat_parser import ChatRuleParser
from app.main import create_app, create_runtime_app
from test_courses import ready, CONTRACT
from test_server_sqlite_integration import stored


class FactProvider:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0
        self.active = 0
        self.enters = 0
        self.exits = 0

    @asynccontextmanager
    async def session(self):
        self.enters += 1
        self.active += 1
        try:
            yield self
        finally:
            self.active -= 1
            self.exits += 1

    async def complete(self, request):
        self.calls += 1
        assert self.active > 0
        assert request.purpose == Purpose.EXPLAIN and request.user_message is None
        assert request.context.mobility == ('STROLLER',)
        assert not request.context.adjustment_items
        assert all(place.allowed_facts for place in request.context.places)
        if self.fail:
            raise RuntimeError('synthetic failure')
        return json.dumps({'items': [{'placeId': p.place_id, 'facts': ['CATEGORY', 'STAY']}
                                    for p in request.context.places]})


def generate(client):
    session = client.post('/api/sessions', json={}).json()
    sid = session['sessionId']
    saved = client.put(f'/api/sessions/{sid}/profile',
        json={'profile': ready(['STROLLER']), 'expectedProfileRevision': 0})
    assert saved.status_code == 200 and saved.json()['status'] == 'READY'
    response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
    assert response.status_code == 200, response.text
    CONTRACT['check'](response.json(), CONTRACT['schemas']['CourseResponse'])
    return response.json()


@pytest.mark.parametrize('fail', [False, True])
def test_runtime_wires_shared_ai_repository_and_executes_explanations(stored, monkeypatch, fail):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    provider = FactProvider(fail=fail)
    ai = AIService(provider)
    app = create_app(connect_real_data=True, extractor=AIConditionExtractor(ai, ChatRuleParser()))
    assert app.state.explanation_generator is None
    with TestClient(app) as client:
        explainer = app.state.explanation_generator
        assert explainer is not None and explainer.ai is ai
        assert explainer.repository is app.state.course_service.repository
        assert app.state.adjustment_interpreter.ai is ai
        assert provider.active == 1  # One outer lifespan for the shared service.
        for _ in range(2):
            body = generate(client)
            assert body['status'] == 'SUCCESS'
            assert {i['reasonMethod'] for i in body['course']['items']} == ({'TEMPLATE'} if fail else {'LLM'})
            warnings = [w for w in body['warnings'] if w['code'] == 'AI_FALLBACK']
            assert bool(warnings) is fail
            if fail:
                assert set(warnings[0]['placeIds']) == {i['place']['id'] for i in body['course']['items']}
        assert provider.calls == (4 if fail else 2)
        assert provider.active == 1
    assert provider.active == 0 and provider.enters == provider.exits
    assert app.state.explanation_generator is None and app.state.course_service is None


def test_runtime_without_model_uses_template_and_explicit_fallback_notice(stored, monkeypatch):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    app = create_runtime_app()
    with TestClient(app) as client:
        assert app.state.explanation_generator.ai is app.state.extractor.ai
        body = generate(client)
        assert all(i['reasonMethod'] == 'TEMPLATE' for i in body['course']['items'])
        assert any(w['code'] == 'AI_FALLBACK' for w in body['warnings'])
    assert app.state.explanation_generator is None


def test_runtime_missing_db_does_not_publish_explainer_or_leak_ai_scope(tmp_path, monkeypatch):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(tmp_path / 'missing.sqlite3'))
    provider = FactProvider()
    app = create_app(connect_real_data=True,
        extractor=AIConditionExtractor(AIService(provider), ChatRuleParser()))
    with pytest.raises(ValueError):
        with TestClient(app):
            pytest.fail('missing DB must prevent startup')
    assert app.state.explanation_generator is None and app.state.course_service is None
    assert provider.calls == 0 and provider.active == 0 and provider.enters == provider.exits
