"""Offline proof of resource reuse, cleanup and unchanged schema semantics."""
import asyncio
from contextlib import asynccontextmanager
import json

import httpx
from pydantic import BaseModel, create_model
import pytest

from app.ai.gemini import GeminiProvider
from app.ai.service import AIService, Purpose
from test_server_sqlite_integration import stored


class Output(BaseModel):
    count: int


def response(*, cookies=False):
    return httpx.Response(200, headers={'set-cookie': 'private-test-cookie=value'} if cookies else {},
        json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"count":1}'}]}}]})


class CountingProvider(GeminiProvider):
    def __init__(self, transport):
        super().__init__('synthetic-key', 'gemini-test', transport=transport)
        self.clients = []

    def _new_client(self):
        client = super()._new_client()
        self.clients.append(client)
        return client


async def call(service):
    return await service.complete(Purpose.EXTRACT, Output, user_message='synthetic')


def test_five_scoped_calls_use_one_client_and_do_not_retain_cookies_or_key_headers():
    requests = []
    def handler(request):
        assert 'cookie' not in request.headers
        assert request.headers['x-goog-api-key'] == 'synthetic-key'
        requests.append(json.loads(request.content))
        return response(cookies=True)
    provider = CountingProvider(httpx.MockTransport(handler))
    async def scenario():
        service = AIService(provider)
        async with service.session():
            for _ in range(5):
                assert (await call(service)).data.count == 1
            assert len(provider.clients) == 1 and not provider.clients[0].is_closed
            assert 'x-goog-api-key' not in provider.clients[0].headers
            assert not provider.clients[0].cookies
        assert provider.clients[0].is_closed and provider._client is None
    asyncio.run(scenario())
    assert len(requests) == 5 and all(body == requests[0] for body in requests)


def test_timeout_retry_uses_same_pool_and_still_cancels_first_attempt():
    calls = 0
    cancelled = False
    async def handler(request):
        nonlocal calls, cancelled
        calls += 1
        if calls == 1:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled = True
                raise
        return response()
    provider = CountingProvider(httpx.MockTransport(handler))
    result = asyncio.run(call(AIService(provider, timeout_seconds=0.01)))
    assert result.data.count == 1 and result.attempts == 2 and cancelled
    assert result.attempt_metrics[0].outcome == 'TIMEOUT'
    assert len(provider.clients) == 1 and provider.clients[0].is_closed


def test_standalone_calls_in_different_event_loops_do_not_reuse_closed_loop_clients():
    provider = CountingProvider(httpx.MockTransport(lambda request: response()))
    service = AIService(provider)
    for _ in range(2):
        assert asyncio.run(call(service)).data.count == 1
    assert len(provider.clients) == 2 and all(c.is_closed for c in provider.clients)


def test_concurrent_calls_share_pool_without_closing_another_requests_client():
    async def handler(request):
        await asyncio.sleep(0)
        return response()
    provider = CountingProvider(httpx.MockTransport(handler))
    async def scenario():
        results = await asyncio.gather(*(call(AIService(provider)) for _ in range(5)))
        assert all(r.data.count == 1 for r in results)
    asyncio.run(scenario())
    assert len(provider.clients) == 1 and provider.clients[0].is_closed


def test_external_cancellation_closes_pool_without_retry():
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return response()
    provider = CountingProvider(httpx.MockTransport(handler))
    async def scenario():
        task = asyncio.create_task(call(AIService(provider)))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert calls == 1 and len(provider.clients) == 1 and provider.clients[0].is_closed


def test_client_setup_failure_keeps_existing_retry_and_sanitization(caplog):
    class BrokenSetup(CountingProvider):
        setups = 0
        def _new_client(self):
            self.setups += 1
            raise RuntimeError('private-setup-sentinel')
    provider = BrokenSetup(httpx.MockTransport(lambda request: response()))
    result = asyncio.run(call(AIService(provider)))
    assert result.failure == 'PROVIDER_FAILURE' and result.attempts == provider.setups == 2
    assert 'private-setup-sentinel' not in caplog.text + repr(result)
    assert provider._client is None and provider._client_users == 0


def test_app_lifespan_keeps_pool_until_shutdown_without_changing_capabilities():
    from app.application.extraction import AIConditionExtractor
    from app.constraints.chat_parser import ChatRuleParser
    from app.main import create_app
    provider = CountingProvider(httpx.MockTransport(lambda request: response()))
    ai = AIService(provider)
    app = create_app(extractor=AIConditionExtractor(ai, ChatRuleParser()))
    async def scenario():
        async with app.router.lifespan_context(app):
            for _ in range(5):
                await call(ai)
            assert len(provider.clients) == 1 and not provider.clients[0].is_closed
            assert not any(app.state.capabilities.model_dump().values())
        assert provider.clients[0].is_closed
    asyncio.run(scenario())


def test_runtime_connection_and_ai_pool_share_lifespan_and_both_close(stored, monkeypatch):
    from app.application.extraction import AIConditionExtractor
    from app.constraints.chat_parser import ChatRuleParser
    from app.main import create_app
    from app.application.profile_support import configured_areas
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    provider = CountingProvider(httpx.MockTransport(lambda request: response()))
    ai = AIService(provider)
    app = create_app(connect_real_data=True, extractor=AIConditionExtractor(ai, ChatRuleParser()))

    async def scenario():
        async with app.router.lifespan_context(app):
            assert app.state.course_service is not None
            assert app.state.course_connection.repository.read_only
            assert app.state.capabilities.supportedAreas == configured_areas()
            for _ in range(2):
                assert (await call(ai)).data.count == 1
            assert len(provider.clients) == 1 and not provider.clients[0].is_closed
        assert provider.clients[0].is_closed
        assert app.state.course_service is None and app.state.course_connection is None
        assert app.state.capabilities.supportedAreas == []

    asyncio.run(scenario())


def test_runtime_startup_failure_unwinds_ai_resource_scope(tmp_path, monkeypatch):
    from app.application.extraction import AIConditionExtractor
    from app.constraints.chat_parser import ChatRuleParser
    from app.main import create_app
    events = []

    class TrackedProvider(CountingProvider):
        @asynccontextmanager
        async def session(self):
            events.append('enter')
            try:
                async with super().session():
                    yield self
            finally:
                events.append('exit')

    monkeypatch.setenv('BUSANFIT_DB_PATH', str(tmp_path / 'missing.sqlite3'))
    provider = TrackedProvider(httpx.MockTransport(lambda request: response()))
    app = create_app(connect_real_data=True,
                     extractor=AIConditionExtractor(AIService(provider), ChatRuleParser()))

    async def scenario():
        with pytest.raises(ValueError):
            async with app.router.lifespan_context(app):
                pytest.fail('missing DB must prevent startup')

    asyncio.run(scenario())
    assert events == ['enter', 'exit']
    assert provider._client_users == 0 and provider._client is None
    assert app.state.course_service is None and app.state.capabilities.supportedAreas == []
    assert not (tmp_path / 'missing.sqlite3').exists()


def test_schema_generation_cached_but_each_request_has_an_independent_copy(monkeypatch):
    schema_calls = 0
    original = Output.model_json_schema
    def counted(**kwargs):
        nonlocal schema_calls
        schema_calls += 1
        return original(**kwargs)
    monkeypatch.setattr(Output, 'model_json_schema', counted)
    seen = []
    class MutatingProvider:
        async def complete(self, request):
            assert 'count' in request.output_schema['properties']
            seen.append(request.output_schema)
            request.output_schema['properties'].clear()
            return 'bad' if len(seen) == 1 else '{"count":1}'
    service = AIService(MutatingProvider())
    async def scenario():
        assert (await call(service)).attempts == 2
        assert (await call(service)).attempts == 1
    asyncio.run(scenario())
    assert schema_calls == 1 and len(seen) == 3
    assert len({id(schema) for schema in seen}) == 3


def test_schema_cache_is_bounded_and_has_no_input_or_response_data():
    class Provider:
        async def complete(self, request): return '{"count":1}'
    service = AIService(Provider())
    async def scenario():
        for index in range(18):
            model = create_model(f'Synthetic{index}', count=(int, ...))
            await service.complete(Purpose.EXTRACT, model, user_message='private-input-sentinel')
    asyncio.run(scenario())
    assert len(service._schema_cache) == 16
    assert 'private-input-sentinel' not in repr(service._schema_cache)


def test_measurement_runner_reuses_one_client_for_five_probes():
    from test_ai_attempt_metrics import probe
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'text': json.dumps(probe.valid_reply())}]} }]})
    provider = CountingProvider(httpx.MockTransport(handler))
    report = asyncio.run(probe.measure(AIService(provider, reference_now=probe.REFERENCE_NOW), runs=5))
    assert report['successfulRuns'] == calls == 5
    assert report['clientLifetime'] == 'measurement-batch'
    assert len(provider.clients) == 1 and provider.clients[0].is_closed
