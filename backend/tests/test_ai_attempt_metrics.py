"""Attempt telemetry privacy and offline measurement; never real model calls."""
import asyncio
from dataclasses import asdict
import importlib.util
import json
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, model_validator
import pytest

from app.ai.fake import FakeProvider, FakeReply
from app.ai.gemini import GeminiProvider
from app.ai.service import AIService, ProviderFailure, Purpose

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('latency_probe', ROOT / 'evaluation/extraction/measure_latency.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid')
    count: int

    @model_validator(mode='after')
    def nonnegative(self):
        if self.count < 0:
            raise ValueError('private-semantic-error-sentinel')
        return self


def complete(provider, *, timeout=0.01):
    return asyncio.run(AIService(provider, timeout_seconds=timeout).complete(
        Purpose.EXTRACT, Output, user_message='private-input-sentinel'))


@pytest.mark.parametrize('raw,detail', [
    ('not-json-private-sentinel', 'INVALID_JSON'),
    ('{"count":"private-output-sentinel"}', 'SCHEMA_VALIDATION'),
    ('{"count":-1}', 'SEMANTIC_VALIDATION'),
    (None, 'NON_TEXT_OUTPUT'),
])
def test_metrics_preserve_failed_attempt_cause_after_success(raw, detail, caplog):
    caplog.set_level(logging.INFO, logger='app.ai.service')
    result = complete(FakeProvider([FakeReply(raw), FakeReply('{"count":1}')]))
    assert result.data.count == 1 and result.failure is None and result.attempts == 2
    first, second = result.attempt_metrics
    assert first.outcome == 'INVALID_OUTPUT' and first.detail == detail and first.retry_reason is None
    assert second.outcome == 'SUCCESS' and second.retry_reason == 'INVALID_OUTPUT'
    assert second.detail == 'NONE'
    text = json.dumps([asdict(m) for m in result.attempt_metrics]) + caplog.text + repr(result)
    assert 'private-' not in text
    for metric in result.attempt_metrics:
        assert metric.provider_ms >= 0 and metric.validation_ms >= 0
        assert abs(metric.elapsed_ms - metric.provider_ms - metric.validation_ms) <= 0.002


def test_timeout_metrics_and_retry_reason():
    provider = FakeProvider([FakeReply(delay_seconds=1), FakeReply('{"count":1}')])
    result = complete(provider)
    assert result.attempt_metrics[0].outcome == 'TIMEOUT'
    assert result.attempt_metrics[0].validation_ms == 0
    assert result.attempt_metrics[1].retry_reason == 'TIMEOUT'
    assert provider.cancelled == 1


def test_attempt_exhaustion_keeps_both_causes():
    class MixedFailure:
        calls = 0
        async def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderFailure('RATE_LIMITED')
            return 'invalid-json'
    result = complete(MixedFailure())
    assert result.data is None and result.failure == 'INVALID_OUTPUT'
    assert [m.detail for m in result.attempt_metrics] == ['RATE_LIMITED', 'INVALID_JSON']
    assert result.attempt_metrics[1].retry_reason == 'PROVIDER_FAILURE'


@pytest.mark.parametrize('status,detail', [(429, 'RATE_LIMITED'), (503, 'UPSTREAM_UNAVAILABLE'), (401, 'HTTP_ERROR')])
def test_http_categories_do_not_capture_body_or_key(status, detail, caplog):
    caplog.set_level(logging.INFO, logger='app.ai.service')
    def handler(request):
        return httpx.Response(status, text='private-provider-body-sentinel')
    provider = GeminiProvider('synthetic-key-sentinel', 'gemini-test', transport=httpx.MockTransport(handler))
    result = complete(provider, timeout=1)
    assert result.failure == 'PROVIDER_FAILURE'
    assert [m.detail for m in result.attempt_metrics] == [detail, detail]
    text = caplog.text + repr(result) + json.dumps([asdict(m) for m in result.attempt_metrics])
    assert 'sentinel' not in text


@pytest.mark.parametrize('kind', ['network', 'invalid-response'])
def test_transport_and_response_errors_have_fixed_categories(kind):
    def handler(request):
        if kind == 'network':
            raise httpx.ConnectError('private-network-sentinel', request=request)
        return httpx.Response(200, json={'private-body-sentinel': 'bad'})
    provider = GeminiProvider('synthetic-key', 'gemini-test', transport=httpx.MockTransport(handler))
    result = complete(provider, timeout=1)
    assert [m.detail for m in result.attempt_metrics] == (['NETWORK_ERROR'] if kind == 'network' else ['INVALID_RESPONSE']) * 2


def test_concurrent_calls_keep_metrics_separate():
    class ConcurrentProvider:
        calls = {}
        async def complete(self, request):
            key = request.user_message
            self.calls[key] = self.calls.get(key, 0) + 1
            first = self.calls[key] == 1
            await asyncio.sleep(0)
            return 'not-json' if key == 'A' and first else '{"count":1}'
    async def scenario():
        service = AIService(ConcurrentProvider())
        return await asyncio.gather(*(service.complete(Purpose.EXTRACT, Output, user_message=key)
                                      for key in ('A', 'B')))
    retried, first_try = asyncio.run(scenario())
    assert [m.outcome for m in retried.attempt_metrics] == ['INVALID_OUTPUT', 'SUCCESS']
    assert [m.outcome for m in first_try.attempt_metrics] == ['SUCCESS']


def test_cancelled_attempt_is_recorded_and_not_retried(caplog):
    caplog.set_level(logging.INFO, logger='app.ai.service')
    async def scenario():
        provider = FakeProvider([FakeReply(delay_seconds=1)])
        task = asyncio.create_task(AIService(provider).complete(Purpose.EXTRACT, Output, user_message='private-input'))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.calls == 1
    asyncio.run(scenario())
    assert 'outcome=CANCELLED' in caplog.text and 'private-input' not in caplog.text


@pytest.mark.parametrize('runs', [5, 10])
def test_offline_probe_counts_first_attempt_retry_and_exhaustion(runs):
    service = AIService(probe.OfflineProbeProvider(runs, 'mixed'), timeout_seconds=1,
                        reference_now=probe.REFERENCE_NOW)
    report = asyncio.run(probe.measure(service, runs=runs))
    assert report['runCount'] == runs
    assert len(report['runs']) == runs
    assert report['retryReasons']['INVALID_OUTPUT'] >= 1
    assert report['retryReasons']['TIMEOUT'] == 1
    if runs == 10:
        assert report['successfulRuns'] == 9 and report['retryRuns'] == 8
        assert report['firstAttemptSuccessCount'] == 2
        assert report['retryReasons']['PROVIDER_FAILURE'] == 2
        assert report['successWithin5SecondsRatio'] == 0.9
    assert all(not r['fallbackExecuted'] for r in report['runs'])
    text = json.dumps(report, ensure_ascii=False)
    for secret in (probe.PROBE_INPUT, '해운대', 'user_message', 'system_prompt', 'output_schema', 'companionHints'):
        assert secret not in text


@pytest.mark.parametrize('runs', [0, 4, 11, True])
def test_invalid_run_count_does_not_contact_provider(runs):
    provider = FakeProvider([])
    with pytest.raises(ValueError, match='5 to 10'):
        asyncio.run(probe.measure(AIService(provider), runs=runs))
    assert provider.calls == 0


def test_fast_failures_are_not_counted_as_fast_model_success():
    report = asyncio.run(probe.measure(AIService(probe.OfflineProbeProvider(5, 'exhausted')), runs=5))
    assert report['successfulRuns'] == report['successWithin5SecondsCount'] == 0
    assert report['retryRuns'] == 5 and report['successWithin5SecondsRatio'] == 0
    assert all(r['fallbackRequired'] for r in report['runs'])


def test_cli_is_offline_only_and_does_not_read_credentials(tmp_path, monkeypatch, capsys):
    import os
    import socket
    class ForbiddenEnvironment(dict):
        def get(self, key, default=None):
            assert not any(word in key.upper() for word in ('GEMINI', 'GOOGLE', 'KEY', 'TOKEN', 'SECRET', 'DOTENV'))
            return default
        def __getitem__(self, key):
            self.get(key)
            raise KeyError(key)
    def forbidden(*args, **kwargs): raise AssertionError('network forbidden')
    # Stub git metadata so no child process environment is needed during this proof.
    monkeypatch.setattr(probe.subprocess, 'check_output', lambda args, **kwargs: 'synthetic-revision' if 'rev-parse' in args else '')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(os, 'environ', ForbiddenEnvironment())
    output = tmp_path / 'offline.json'
    assert probe.main(['--runs', '5', '--scenario', 'success', '--output', str(output)]) == 0
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['syntheticOnly'] and not report['realModelMeasured'] and not report['performanceEvidence']
    assert report['providerKind'] == 'OFFLINE_FAKE' and report['runCount'] == 5
    assert 'private-' not in output.read_text() + capsys.readouterr().out
