"""Explanation through real HTTP handlers and Gemini wire adapter with no network."""
import json
from dataclasses import replace
import httpx
import pytest
from app.ai.gemini import GeminiProvider, UnconfiguredProvider
from app.ai.service import AIService
from app.explanations.generator import ExplanationGenerator
from test_courses import env, seed, generate, check_contract


class SelectFacts:
    calls = 0
    async def complete(self, request):
        self.calls += 1
        return json.dumps({'items': [{'placeId': p.place_id, 'facts': ['CATEGORY', 'STAY']}
                                     for p in request.context.places]})


def connect(env, provider, **kwargs):
    env['app'].state.explanation_generator = ExplanationGenerator(AIService(provider), env['repository'], **kwargs)


def test_course_explanations_and_detail_share_place_source_payloads(env):
    seed(env)
    provider = SelectFacts()
    connect(env, provider)
    response = generate(env)
    check_contract(response)
    course = response.json()['course']
    assert provider.calls == 1
    for item in course['items']:
        assert item['reasonMethod'] == 'LLM'
        detail = env['client'].get('/api/places/' + item['place']['id'])
        assert detail.status_code == 200
        assert detail.json()['place'] == item['place']
        assert all(source in course['sources'] for source in detail.json()['sources'])
    assert env['store'].check_current(env['sid'], 1).profile


def test_real_gemini_wire_serializes_only_bounded_context_and_schema(env):
    seed(env)
    def handler(request):
        body = json.loads(request.content)
        assert request.headers['x-goog-api-key'] == 'synthetic-key'
        context = json.loads(body['contents'][0]['parts'][0]['text'])
        assert set(context) == {'place_ids', 'places', 'mobility'}
        assert all(set(p) == {'place_id', 'name', 'category', 'overview', 'allowed_facts'} for p in context['places'])
        assert 'sessionId' not in str(context) and 'hasInfant' not in str(context)
        assert body['generationConfig']['temperature'] == 0.2
        assert body['generationConfig']['responseJsonSchema']['properties']['items']
        answer = json.dumps({'items': [{'placeId': key, 'facts': ['STAY']} for key in context['place_ids']]})
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': answer}]}}]})
    connect(env, GeminiProvider('synthetic-key', 'gemini-test-flash', transport=httpx.MockTransport(handler)))
    body = generate(env).json()
    assert body['status'] == 'SUCCESS'
    assert all(i['reasonMethod'] == 'LLM' for i in body['course']['items'])


def test_llm_unavailable_still_returns_valid_course_and_notice(env):
    seed(env)
    connect(env, UnconfiguredProvider())
    response = generate(env)
    check_contract(response)
    body = response.json()
    assert body['status'] == 'SUCCESS'
    assert all(i['reasonMethod'] == 'TEMPLATE' for i in body['course']['items'])
    assert any(w['code'] == 'AI_FALLBACK' for w in body['warnings'])


def test_insufficient_places_never_calls_explanation_provider(env):
    seed(env)
    env['retriever'].places = env['retriever'].places[:1]
    provider = SelectFacts()
    connect(env, provider)
    assert generate(env).json()['status'] == 'INSUFFICIENT_PLACES'
    assert provider.calls == 0


@pytest.mark.parametrize('race', ['revision', 'expiry', 'deletion'])
@pytest.mark.parametrize('fail', [False, True])
def test_slow_explanation_does_not_override_session_guards(env, race, fail):
    seed(env)
    class Race(SelectFacts):
        async def complete(self, request):
            if race == 'revision':
                state = env['store'].check_current(env['sid'], 1)
                env['store'].commit_profile(env['sid'], 1, profile=state.profile, history=[])
            elif race == 'expiry': env['now'][0] = 1800
            else: env['store'].clear()
            if fail: raise RuntimeError('private-sentinel')
            return await super().complete(request)
    connect(env, Race())
    response = generate(env)
    assert response.status_code == (409 if race == 'revision' else 410)
    assert 'private-sentinel' not in response.text


def test_repository_race_is_500_without_renewing_ttl(env):
    seed(env)
    before = env['store'].check_current(env['sid'], 1)
    class Mutate(SelectFacts):
        async def complete(self, request):
            p = env['places'][0]
            env['repository'].places[p.id] = replace(p, indoor=False)
            env['now'][0] = 100
            return await super().complete(request)
    connect(env, Mutate())
    response = generate(env)
    assert response.status_code == 500
    assert env['store'].check_current(env['sid'], 1).expires_at == before.expires_at
