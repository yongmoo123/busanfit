"""5–10 sequential extraction probes. CLI is offline-only; never loads credentials."""
import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.ai.service import AIService, ProviderFailure, Purpose
from app.application.extraction import ExtractionOutput, blank_profile

REFERENCE_NOW = datetime(2026, 11, 20, 10, tzinfo=timezone(timedelta(hours=9)))
PROBE_ID = 'LAT-01'
PROBE_INPUT = '[가상] 11월 23일 오후 1시부터 5시까지 해운대에서 친구와 둘이 도보로 갈게요. 영유아는 없어요.'
SCENARIOS = ('success', 'invalid-json', 'schema', 'semantic', 'timeout', 'rate-limit', 'provider-error', 'exhausted', 'mixed')


def valid_reply():
    values = blank_profile()
    for name, value, strength in (
        ('area', 'HAEUNDAE', 'HARD'),
        ('timeWindow', {'startAt': '2026-11-23T13:00:00+09:00', 'endAt': '2026-11-23T17:00:00+09:00'}, 'HARD'),
        ('transport', 'WALK', 'SOFT'),
        ('companions', {'type': 'FRIENDS', 'count': 2, 'hasInfant': False}, 'SOFT'),
    ):
        values[name] = {'value': value, 'source': 'USER', 'strength': strength}
    return {'profile': values, 'unconfirmedFields': [], 'companionHints': {}}


class OfflineProbeProvider:
    """A deliberate fake. No sockets, key/config reads or stored requests."""
    def __init__(self, runs, scenario):
        if scenario not in SCENARIOS:
            raise ValueError('unknown offline scenario')
        self.actions = []
        kinds = ('success', 'invalid-json', 'schema', 'semantic', 'timeout', 'rate-limit', 'provider-error', 'exhausted')
        for index in range(runs):
            kind = kinds[index % len(kinds)] if scenario == 'mixed' else scenario
            self.actions.extend(['success'] if kind == 'success' else
                                ['invalid-json', 'invalid-json'] if kind == 'exhausted' else [kind, 'success'])

    async def complete(self, request):
        action = self.actions.pop(0)
        await asyncio.sleep(0)
        if action == 'timeout':
            raise TimeoutError('offline timeout simulation')
        if action == 'rate-limit':
            raise ProviderFailure('RATE_LIMITED')
        if action == 'provider-error':
            raise RuntimeError('offline failure; never persist exception text')
        if action == 'invalid-json':
            return 'not-json'
        payload = valid_reply()
        if action == 'schema':
            payload['profile']['mobility']['strength'] = 'SOFT'
        if action == 'semantic':
            payload['profile']['timeWindow']['value']['endAt'] = '2026-11-23T12:00:00+09:00'
        return json.dumps(payload, ensure_ascii=False)


def percentile(values, fraction):
    """Nearest rank; small diagnostic sample, not a production latency estimate."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


async def measure(service: AIService, *, runs=5):
    """Caller injects the service. This function never creates a live provider.

    Measures the AI boundary including retry/validation, not HTTP/chat/rule fallback.
    Keep report classification outside this function explicit about the provider.
    """
    if type(runs) is not int or not 5 <= runs <= 10:
        raise ValueError('runs must be an integer from 5 to 10')
    records = []
    async with service.session():
        for index in range(runs):
            started = perf_counter()
            result = await service.complete(Purpose.EXTRACT, ExtractionOutput, user_message=PROBE_INPUT)
            elapsed = (perf_counter() - started) * 1000
            records.append({'run': index + 1, 'inputId': PROBE_ID, 'elapsedMs': round(elapsed, 3),
                            'modelResponseValid': result.data is not None, 'failure': result.failure,
                            'attemptCount': result.attempts,
                            'attempts': [asdict(metric) for metric in result.attempt_metrics],
                            'fallbackRequired': result.data is None, 'fallbackExecuted': False})
    elapsed = [r['elapsedMs'] for r in records]
    retry_reasons = Counter(metric['retry_reason'] for r in records for metric in r['attempts'] if metric['retry_reason'])
    failures = Counter(metric['detail'] for r in records for metric in r['attempts'] if metric['outcome'] not in ('SUCCESS', 'CANCELLED'))
    return {'runCount': runs, 'targetMs': 5000, 'measurementScope': 'ai-boundary-with-retries-and-validation',
            'clientLifetime': 'measurement-batch',
            'firstAttemptSuccessCount': sum(r['modelResponseValid'] and r['attemptCount'] == 1 for r in records),
            'successfulRuns': sum(r['modelResponseValid'] for r in records),
            'retryRuns': sum(r['attemptCount'] > 1 for r in records),
            'successWithin5SecondsCount': sum(r['modelResponseValid'] and r['elapsedMs'] <= 5000 for r in records),
            'successWithin5SecondsRatio': sum(r['modelResponseValid'] and r['elapsedMs'] <= 5000 for r in records) / runs,
            'latencyMs': {'mean': sum(elapsed) / runs, 'p50': percentile(elapsed, 0.5),
                          'p90': percentile(elapsed, 0.9), 'max': max(elapsed)},
            'retryReasons': dict(retry_reasons), 'attemptFailureDetails': dict(failures), 'runs': records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, choices=range(5, 11), default=5)
    parser.add_argument('--scenario', choices=SCENARIOS, default='mixed')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    # No Gemini import/configured_provider/load_dotenv/os.environ or live CLI mode.
    service = AIService(OfflineProbeProvider(args.runs, args.scenario), reference_now=REFERENCE_NOW)
    report = asyncio.run(measure(service, runs=args.runs))
    report.update({'syntheticOnly': True, 'providerKind': 'OFFLINE_FAKE', 'modelVersion': 'none-offline-probe',
        'realModelMeasured': False, 'performanceEvidence': False, 'fakeScenario': args.scenario,
        'attemptTimeoutMs': 10000, 'referenceNow': REFERENCE_NOW.isoformat(),
        'runAt': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('providerKind', 'runCount', 'successfulRuns',
        'retryRuns', 'retryReasons', 'realModelMeasured', 'performanceEvidence')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
