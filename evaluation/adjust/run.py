"""Score modification intent interpretation (AI-REQ-07) on the PM's synthetic set.

Calls the real AdjustmentInterpreter (#86) with the shared [가상] base course.
Only intent is scored here; AC-007 rescheduling is covered by backend tests and
the live adjust check, and is recorded separately. Rule results are not LLM
accuracy evidence. Never prints or stores the API key or raw model output.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.ai.gemini import GeminiProvider, UnconfiguredProvider  # noqa: E402
from app.ai.service import AIService  # noqa: E402
from app.application.adjustment_interpreter import AdjustmentInterpreter  # noqa: E402

# The interpreter receives no suggestion context (FR-013 acceptance goes through the
# explicit consent UI, DEC-033), so a bare "네" cannot be scored as INCLUDE_UNKNOWN.
EXCLUDED = {'AD-16': '직전 제안 문맥(lastSuggestion)을 해석기에 넘기는 경로가 없다. '
                     'FR-013 수락은 채팅이 아니라 명시적 동의 화면으로 처리한다(DEC-033, #30).'}


def base_course(dataset, mobility=None):
    date = dataset['baseCourse']['date']
    items = []
    for item in dataset['baseCourse']['items']:
        at = lambda hm: datetime.fromisoformat(f'{date}T{hm}:00+09:00')  # noqa: E731
        items.append(SimpleNamespace(order=item['order'], startAt=at(item['startAt']), endAt=at(item['endAt']),
                                     place=SimpleNamespace(name=item['name'], category=item['category'],
                                                           indoor=item['indoor'])))
    profile = SimpleNamespace(mobility=SimpleNamespace(value=[mobility] if mobility else None))
    return SimpleNamespace(items=items), profile


def same_op(actual, expected):
    """op, targets (None = not scored) and the params the case names."""
    if actual['op'] != expected['op']:
        return False
    if expected.get('targets') is not None and sorted(actual['targets']) != sorted(expected['targets']):
        return False
    for key, value in (expected.get('params') or {}).items():
        if actual.get(key) != value:
            return False
    if expected.get('field') is not None and actual.get('field') != expected['field']:
        return False
    return True


def matches(actual, expected, acceptable=()):
    """``acceptable`` sits at case level in cases.json (alternatives to ``expected``)."""
    options = [expected, *acceptable]
    if not any(same_op(actual, option) for option in options):
        return False
    follow = expected.get('followUp')
    if follow is not None:
        rest = actual.get('followUp') or []
        return bool(rest) and same_op(rest[0], follow)
    return True


def mobility_of(case):
    before = (case.get('before') or {}).get('mobility') or ''
    return before.split('(')[0] or None


async def evaluate(dataset, interpreter, delay=0.0):
    records = []
    for n, case in enumerate(dataset['cases']):
        record = {'id': case['id'], 'category': case['category']}
        if case['id'] in EXCLUDED:
            record.update(verdict='EXCLUDED', reason=EXCLUDED[case['id']])
            records.append(record)
            continue
        if n and delay:
            await asyncio.sleep(delay)
        course, profile = base_course(dataset, mobility_of(case))
        message = case['input'].removeprefix('[가상]').strip()
        start = time.perf_counter()
        result = await interpreter.interpret(message, course, profile)
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        actual = result.intent.model_dump(mode='json')
        ok = matches(actual, case['expected'], case.get('acceptable', ()))
        record.update(actual=actual, fallback=result.fallback, interpretMs=elapsed,
                      verdict='PASS' if ok else 'FAIL',
                      manualReviewRequired=case['expected'].get('mustNot', []))
        records.append(record)
    scored = [r for r in records if r['verdict'] != 'EXCLUDED']
    correct = sum(r['verdict'] == 'PASS' for r in scored)
    llm_ms = sorted(r['interpretMs'] for r in scored if not r['fallback'])
    return {'intentAccuracy': {'correct': correct, 'total': len(scored),
                               'ratio': correct / len(scored) if scored else None},
            'excluded': [r['id'] for r in records if r['verdict'] == 'EXCLUDED'],
            'fallbackCases': [r['id'] for r in scored if r['fallback']],
            'latency': {'llmCases': len(llm_ms), 'maxMs': llm_ms[-1] if llm_ms else None,
                        'meanMs': round(sum(llm_ms) / len(llm_ms), 1) if llm_ms else None},
            'cases': records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=('rules', 'gemini'), default='rules')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--delay', type=float, default=0.0, help='seconds between cases (free tier, DEC-030)')
    args = parser.parse_args()
    dataset = json.loads(Path(__file__).with_name('cases.json').read_text(encoding='utf-8'))
    if args.provider == 'gemini':
        from dotenv import load_dotenv
        load_dotenv(ROOT / 'backend/.env')
        key, model = os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')
        if not key or not model:
            parser.error('Set GEMINI_API_KEY and GEMINI_MODEL before live synthetic evaluation.')
        provider = GeminiProvider(key, model)
    else:
        provider, model = UnconfiguredProvider(), 'adjust-rule-fallback'
    interpreter = AdjustmentInterpreter(AIService(provider, reference_now=datetime.fromisoformat(dataset['referenceNow'])))
    report = asyncio.run(evaluate(dataset, interpreter, args.delay))
    report.update({'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
                   'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                   'datasetVersion': dataset.get('version'), 'provider': args.provider, 'modelVersion': model,
                   'syntheticOnly': True, 'delaySeconds': args.delay,
                   'llmAccuracyMeasured': args.provider == 'gemini' and not report['fallbackCases'],
                   'scope': 'intent only (AI-REQ-07); AC-007 rescheduling recorded separately',
                   'mustNotChecks': 'manual review required; excluded from automatic verdict'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('provider', 'intentAccuracy', 'excluded', 'fallbackCases',
                                             'llmAccuracyMeasured', 'latency')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
