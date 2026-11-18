"""Synthetic JSON and network-free provider behavior; no real model calls."""
import asyncio
from dataclasses import FrozenInstanceError
import pytest
from pydantic import BaseModel, ConfigDict
from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService, CourseContext, Purpose


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid')
    count: int


def run(provider, **kwargs):
    return asyncio.run(AIService(provider, timeout_seconds=0.01).complete(
        Purpose.EXTRACT, Output, user_message='synthetic', **kwargs))


def test_success_validates_json_without_retry():
    provider = FakeProvider([FakeReply('{"count":2}')])
    result = run(provider)
    assert result.data.count == 2 and result.failure is None
    assert result.attempts == provider.calls == 1


@pytest.mark.parametrize('invalid', ['not-json', '{"count":"2"}', '{"count":true}', '{"extra":2}', '{"count":2,"extra":3}'])
def test_invalid_output_retried_once(invalid):
    provider = FakeProvider([FakeReply(invalid), FakeReply('{"count":3}')])
    result = run(provider)
    assert result.data.count == 3
    assert result.attempts == provider.calls == 2


def test_retry_exhaustion_returns_typed_failure_not_fake_success():
    provider = FakeProvider([FakeReply('bad'), FakeReply('bad'), FakeReply('{"count":3}')])
    result = run(provider)
    assert result.data is None and result.failure == 'INVALID_OUTPUT'
    assert result.attempts == provider.calls == 2


def test_timeout_cancels_both_attempts():
    provider = FakeProvider([FakeReply(delay_seconds=1), FakeReply(delay_seconds=1)])
    result = run(provider)
    assert result.failure == 'TIMEOUT' and result.data is None
    assert provider.calls == provider.cancelled == 2


def test_timeout_can_recover_on_second_attempt():
    provider = FakeProvider([FakeReply(delay_seconds=1), FakeReply('{"count":1}')])
    assert run(provider).data.count == 1
    assert provider.cancelled == 1


def test_provider_failure_is_sanitized(caplog, capsys):
    class Broken:
        calls = 0

        async def complete(self, request):
            self.calls += 1
            raise RuntimeError('private-sentinel')

    provider = Broken()
    result = run(provider)
    assert provider.calls == 2 and result.failure == 'PROVIDER_FAILURE'
    assert 'private-sentinel' not in repr(result) + caplog.text + capsys.readouterr().out


def test_external_cancellation_is_not_retried():
    async def scenario():
        provider = FakeProvider([FakeReply(delay_seconds=10)])
        task = asyncio.create_task(AIService(provider).complete(Purpose.EXTRACT, Output, user_message='synthetic'))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.calls == 1
    asyncio.run(scenario())


def test_purpose_and_context_boundary():
    class Inspect:
        async def complete(self, request):
            assert request.user_message is None
            assert request.context.mobility == ('WHEELCHAIR',)
            assert request.output_schema['properties']['count']['type'] == 'integer'
            assert request.purpose == Purpose.EXPLAIN
            assert '장소·가격·시간·출처를 만들지' in request.system_prompt
            return '{"count":1}'

    result = asyncio.run(AIService(Inspect()).complete(Purpose.EXPLAIN, Output,
        context=CourseContext(('synthetic-place',), ('WHEELCHAIR',))))
    assert result.data.count == 1


@pytest.mark.parametrize('purpose,message,context', [
    (Purpose.EXPLAIN, 'private-sentinel', None),
    (Purpose.EXTRACT, None, None),
    (Purpose.MODIFY, None, None),
    ('unknown', 'synthetic', None),
    (Purpose.MODIFY, 'synthetic', 'private-sentinel'),
])
def test_invalid_call_does_not_contact_provider(purpose, message, context):
    provider = FakeProvider([])
    with pytest.raises(ValueError):
        asyncio.run(AIService(provider).complete(purpose, Output, user_message=message, context=context))
    assert provider.calls == 0


def test_context_rejects_raw_health_categories_and_is_immutable():
    with pytest.raises(ValueError):
        CourseContext(mobility=('private-sentinel',))
    context = CourseContext(mobility=('INJURY',))
    with pytest.raises(FrozenInstanceError):
        context.mobility = ('STROLLER',)


def test_request_repr_does_not_expose_prompt_and_retry_gets_schema_hint():
    class Inspect:
        calls = 0

        async def complete(self, request):
            self.calls += 1
            assert 'private-sentinel' not in repr(request)
            if self.calls == 1:
                return 'private-sentinel'
            assert '다시 생성' in request.system_prompt
            return '{"count":1}'

    result = asyncio.run(AIService(Inspect()).complete(Purpose.MODIFY, Output, user_message='private-sentinel'))
    assert result.attempts == 2


def test_default_timeout_is_ten_seconds():
    assert AIService(FakeProvider([]))._timeout == 10
    with pytest.raises(ValueError):
        AIService(FakeProvider([]), timeout_seconds=0)


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), -float('inf'),
    True, False, 0, -1, '10', None, 10**400])
def test_invalid_timeout_is_rejected_before_provider_calls(timeout):
    provider = FakeProvider([])
    with pytest.raises(ValueError, match='positive finite number'):
        AIService(provider, timeout_seconds=timeout)
    assert provider.calls == 0


@pytest.mark.parametrize('timeout', [1, 0.01])
def test_positive_finite_timeout_still_allows_calls(timeout):
    provider = FakeProvider([FakeReply('{"count":1}')])
    result = asyncio.run(AIService(provider, timeout_seconds=timeout).complete(
        Purpose.EXTRACT, Output, user_message='synthetic'))
    assert result.data.count == 1 and result.attempts == 1


def test_schema_correction_only_includes_known_field_names():
    class Inspect:
        calls = 0

        async def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                return '{"count":"private-sentinel","private-sentinel":1}'
            assert '확인할 필드: count' in request.system_prompt
            assert 'private-sentinel' not in request.system_prompt
            return '{"count":1}'

    assert run(Inspect()).data.count == 1
