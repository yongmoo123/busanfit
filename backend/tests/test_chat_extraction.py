"""Synthetic messages; HTTP mocks exercise the real provider adapter offline."""
import asyncio
import json
import logging

import httpx
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.ai.gemini import GeminiProvider, UnconfiguredProvider, configured_provider
from app.ai.service import AIService, Purpose
from app.application.extraction import AIConditionExtractor, ExtractionOutput, blank_profile
from app.constraints.chat_parser import ChatRuleParser
from app.main import create_app


def run(coro):
    return asyncio.run(coro)


def enabled_app(extractor=None):
    app = create_app(extractor=extractor)
    app.state.capabilities.supportedAreas = ['HAEUNDAE']
    app.state.capabilities.supportedTransports = ['WALK']
    app.state.capabilities.supportedProfileFields = list(blank_profile())[:-1]
    return app


def test_gemini_wire_schema_header_and_text_parts(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request):
        assert request.url.scheme == 'https'
        assert 'key' not in request.url.params
        assert request.headers['x-goog-api-key'] == 'synthetic-key'
        body = json.loads(request.content)
        assert body['contents'][0]['parts'][0]['text'] == 'synthetic-health-sentinel'
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert 'properties' in body['generationConfig']['responseJsonSchema']
        assert '장소 추천' in body['systemInstruction']['parts'][0]['text']
        value = json.dumps({'profile': blank_profile()})
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'text': 'private-thought', 'thought': True}, {'text': value[:20]}, {'text': value[20:]},
        ]}}]})

    provider = GeminiProvider('synthetic-key', 'gemini-test-flash', transport=httpx.MockTransport(handler))
    result = run(AIService(provider).complete(Purpose.EXTRACT, ExtractionOutput,
                                            user_message='synthetic-health-sentinel'))
    assert result.data is not None and result.attempts == 1
    assert 'synthetic-key' not in repr(provider) + caplog.text
    assert 'synthetic-health-sentinel' not in caplog.text + repr(result)


@pytest.mark.parametrize('response', [
    httpx.Response(429, text='private-error-sentinel'),
    httpx.Response(200, json={'candidates': []}),
    httpx.Response(200, json={'candidates': [{'finishReason': 'MAX_TOKENS'}]}),
    httpx.Response(200, text='not-json'),
])
def test_provider_failure_retries_then_falls_back_without_leaks(response, caplog):
    calls = []
    def handler(request):
        calls.append(1)
        return response
    provider = GeminiProvider('synthetic-key', 'gemini-test-flash', transport=httpx.MockTransport(handler))
    extractor = AIConditionExtractor(AIService(provider), ChatRuleParser())
    result = run(extractor.extract('해운대'))
    assert len(calls) == 2
    assert result.fallback and result.profile['area']['value'] == 'HAEUNDAE'
    assert 'private-error-sentinel' not in caplog.text + repr(result)


def test_provider_transport_timeout_reaches_rule_fallback():
    def handler(request):
        raise httpx.ReadTimeout('synthetic-private-error')
    provider = GeminiProvider('synthetic-key', 'gemini-test-flash', transport=httpx.MockTransport(handler))
    result = run(AIConditionExtractor(AIService(provider), ChatRuleParser()).extract('해운대'))
    assert result.fallback and result.failure == 'TIMEOUT'


def test_provider_configuration_is_explicit(monkeypatch):
    assert isinstance(configured_provider(), UnconfiguredProvider)
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-test-flash')
    assert isinstance(configured_provider(), GeminiProvider)
    with pytest.raises(ValueError):
        GeminiProvider('synthetic-key', '../../other-host')


@pytest.mark.parametrize('message,field,value,strength', [
    ('실내 위주', 'indoor_preference', 'INDOOR', 'SOFT'),
    ('꼭 실내에서만', 'indoor_preference', 'INDOOR', 'HARD'),
    ('실외는 절대 안 돼', 'indoor_preference', 'INDOOR', 'HARD'),
    ('카페는 빼줘', 'excluded_categories', ('CAFE',), 'HARD'),
    ('발목을 다쳤어', 'mobility', ('INJURY',), 'HARD'),
])
def test_explicit_fallback_grammars(message, field, value, strength):
    result = ChatRuleParser().parse(message)
    assert result.conditions[field].value == value
    assert result.conditions[field].strength == strength
    assert field not in result.unconfirmed_fields


def test_ambiguous_mobility_is_not_cleared_by_injury_clause():
    result = ChatRuleParser().parse('유모차는 안 써, 발목을 다쳤어')
    assert 'mobility' in result.unconfirmed_fields


def test_semantic_invalid_ai_time_is_retried_before_rules():
    profile = blank_profile()
    profile['timeWindow'] = {'value': {'startAt': '2026-11-13T17:00:00+09:00',
                                     'endAt': '2026-11-13T13:00:00+09:00'},
                             'source': 'USER', 'strength': 'HARD'}
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate({'profile': profile})


def test_conflicting_ai_infant_hints_are_rejected():
    profile = blank_profile()
    profile['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': False},
                              'source': 'USER', 'strength': 'SOFT'}
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate({'profile': profile, 'companionHints': {'hasInfant': True}})


def test_successful_ai_uses_walk_default_but_unconfirmed_transport_does_not():
    from app.ai.fake import FakeProvider, FakeReply
    profile = blank_profile()
    profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
    provider = FakeProvider([FakeReply(json.dumps({'profile': profile})),
                             FakeReply(json.dumps({'profile': profile, 'unconfirmedFields': ['transport']}))])
    extractor = AIConditionExtractor(AIService(provider), ChatRuleParser())
    with TestClient(enabled_app(extractor)) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        first = client.post('/api/chat', json={'sessionId': sid, 'message': '해운대', 'expectedProfileRevision': 0})
        assert first.json()['profile']['transport'] == {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}
        second = client.post('/api/chat', json={'sessionId': sid, 'message': '이동 변경 가상 입력', 'expectedProfileRevision': 1})
        assert second.json()['status'] == 'NEEDS_INPUT'
        assert any(w['code'] == 'UNCONFIRMED_CHANGE' for w in second.json()['warnings'])


def test_real_chat_route_partial_merge_and_unsupported_transport_acceptance():
    with TestClient(enabled_app()) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        def chat(message, revision):
            response = client.post('/api/chat', json={'sessionId': sid, 'message': message,
                                                      'expectedProfileRevision': revision})
            assert response.status_code == 200, response.text
            return response.json()
        first = chat('해운대, 2026-11-13 13시부터 17시까지, 자차로 이동', 0)
        assert first['status'] == 'NEEDS_INPUT'
        second = chat('도보로 이동할게요', 1)
        assert second['status'] == 'READY'
        third = chat('카페는 빼줘', 2)
        assert third['profile']['timeWindow'] == first['profile']['timeWindow']
        assert third['profile']['excludedCategories']['value'] == ['CAFE']
        assert third['status'] == 'READY'
        fourth = chat('공원은 빼줘', 3)
        assert fourth['profile']['excludedCategories']['value'] == ['CAFE', 'PARK']
        assert fourth['profile']['timeWindow'] == first['profile']['timeWindow']


def test_normal_server_does_not_activate_unverified_course_capabilities():
    with TestClient(create_app()) as client:
        session = client.post('/api/sessions', json={}).json()
        assert not any(session['capabilities'].values())
        assert '/api/chat' in client.get('/openapi.json').json()['paths']


def test_dec022_family_infant_question_once_then_warning_without_count_guess():
    with TestClient(enabled_app()) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        def chat(message, revision):
            response = client.post('/api/chat', json={'sessionId': sid, 'message': message,
                                                      'expectedProfileRevision': revision})
            assert response.status_code == 200, response.text
            return response.json()
        first = chat('해운대, 2026-11-13 13시부터 17시까지, 가족끼리', 0)
        assert first['status'] == 'NEEDS_INPUT'
        assert [q['field'] for q in first['questions']] == ['companions']
        assert first['profile']['companions']['value'] is None
        assert first['profile']['mobility']['value'] is None
        second = chat('실내 위주', 1)
        assert second['status'] == 'READY' and second['questions'] == []
        assert second['profile']['companions']['value'] is None
        assert any(w['code'] == 'UNCONFIRMED_CHANGE' and '영유아' in w['message'] for w in second['warnings'])
        third = chat('아기 동반', 2)
        assert third['profile']['mobility']['value'] == ['STROLLER']
        assert third['status'] == 'READY'
        assert not any('영유아 동반이면' in w['message'] for w in third['warnings'])


def test_dec022_question_hidden_by_missing_required_fields_is_not_consumed():
    with TestClient(enabled_app()) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        # Normal AI, because rule fallback with both required fields absent is 503.
        from app.application.extraction import Analysis
        class Partial:
            async def extract(self, message):
                return Analysis(blank_profile(), companion_hints={'type': 'FAMILY'})
        client.app.state.extractor = Partial()
        body = {'sessionId': sid, 'message': '가족끼리', 'expectedProfileRevision': 0}
        first = client.post('/api/chat', json=body).json()
        assert [q['field'] for q in first['questions']] == ['area', 'timeWindow']
        state = client.app.state.sessions.check_current(sid, 1)
        assert not state.companion_hints.get('_infantAsked')
        assert state.pending_fields['companions'] == 'INFANT_CONFIRMATION'


def test_partial_companion_change_preserves_existing_explicit_infant_value():
    with TestClient(enabled_app()) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        from test_chat_policy import ready, condition
        profile = ready()
        profile['companions'] = condition({'type': 'FAMILY', 'count': 3, 'hasInfant': True}, 'SOFT')
        client.app.state.sessions.commit_profile(sid, 0, profile=profile, history=[])
        response = client.post('/api/chat', json={'sessionId': sid, 'message': '친구 4명', 'expectedProfileRevision': 1})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['profile']['companions']['value']['hasInfant'] is True
        assert body['profile']['mobility']['value'] == ['STROLLER']


@pytest.mark.parametrize('message,count,kind', [('혼자', 1, 'SOLO'), ('연인', 2, 'COUPLE'), ('친구 4명', 4, 'FRIENDS')])
def test_dec022_known_nonfamily_does_not_ask_about_infants(message, count, kind):
    with TestClient(enabled_app()) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        response = client.post('/api/chat', json={'sessionId': sid,
            'message': f'해운대, 2026-11-13 13시부터 17시까지, {message}', 'expectedProfileRevision': 0})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] == 'READY' and body['questions'] == []
        assert body['profile']['companions']['value'] == {'type': kind, 'count': count, 'hasInfant': False}
