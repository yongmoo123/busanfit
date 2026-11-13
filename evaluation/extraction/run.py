"""Score the PM's synthetic draft. Rule results are not LLM accuracy evidence."""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.ai.gemini import GeminiProvider, UnconfiguredProvider
from app.ai.service import AIService
from app.api.session_models import Capabilities
from app.application.condition_policy import analyze_chat
from app.application.extraction import AIConditionExtractor, blank_profile
from app.constraints.chat_parser import ChatRuleParser
from app.constraints.profile import ProfileError
from app.sessions.store import SessionSnapshot


def matches(actual, expected, *, strength=False):
    if 'acceptable' in expected:
        choices = expected['acceptable']
        if choices and isinstance(choices[0], dict) and 'value' in choices[0]:
            return any(matches(actual, choice, strength=strength) for choice in choices)
        if not strength and actual['value'] in choices and actual['source'] == expected.get('source', 'USER'):
            return True
    if strength:
        return expected.get('strength') is None or actual['strength'] == expected['strength']
    if 'keywordsAny' in expected:
        return actual['source'] == expected.get('source', 'USER') and any(
            keyword in ' '.join(actual['value'] or []) for keyword in expected['keywordsAny'])
    return actual['value'] == expected.get('value') and actual['source'] == expected.get('source', 'USER')


async def evaluate(dataset, extractor):
    records = []
    fields = list(blank_profile())[:-1]
    for case in dataset['cases']:
        analysis = await extractor.extract(case['input'])
        expected = case['expected']
        field_results = {name: matches(analysis.profile[name], expected['extracted'][name])
                         if name in expected['extracted'] else analysis.profile[name]['source'] != 'USER'
                         for name in fields}
        strengths = {name: matches(analysis.profile[name], value, strength=True)
                     for name, value in expected['extracted'].items()
                     if 'strength' in value or 'acceptable' in value}
        caps_data = case['before']['capabilities']
        caps = Capabilities(**{key: value for key, value in dataset['capabilities'][caps_data].items() if key != 'note'},
                            supportsUnknownAccessibilityInclusion=False,
                            supportsCourseAdjustment=False, supportsWeather=False)
        profile = blank_profile()
        profile.update(deepcopy(case['before']['profileOverrides']))
        pending = {item['field']: item['reason'] for item in case['before']['pendingFields']}
        state = SessionSnapshot('synthetic', datetime.fromisoformat(dataset['referenceNow']),
                                profile=profile, pending_fields=pending)
        try:
            result = analyze_chat(state, analysis, caps)
            actual = {'httpStatus': 503 if result.unavailable else 200,
                      'status': None if result.unavailable else ('NEEDS_INPUT' if result.questions or result.pending else 'READY'),
                      'profile': result.profile.model_dump(mode='json'),
                      'questions': [] if result.unavailable else result.questions,
                      'warnings': [] if result.unavailable else result.warnings}
            actual['pendingFields'] = result.pending
        except ProfileError as error:
            actual = {'httpStatus': 422, 'code': error.code, 'questions': [], 'warnings': []}
        policy_checks = {'status': actual.get('status') == expected.get('status'),
                         'questionFields': [q['field'] for q in actual['questions']] == expected.get('questionFields', []),
                         'warningCodes': set(expected.get('warningCodes', [])) <= {w['code'] for w in actual['warnings']}}
        for name, value in expected.get('policy', {}).items():
            if name == 'pendingCleared':
                policy_checks[name] = all(field not in actual.get('pendingFields', {}) for field in value)
                continue
            if 'applied' in value:
                policy_checks[name] = (actual.get('profile', blank_profile())[name]['value'] == profile[name]['value']) if not value['applied'] else False
                continue
            policy_checks[name] = matches(actual.get('profile', blank_profile())[name], value) and matches(
                actual.get('profile', blank_profile())[name], value, strength=True)
        for name in expected.get('unchanged', []):
            policy_checks['unchanged.' + name] = actual.get('profile', {}).get(name) == profile[name]
        records.append({'id': case['id'], 'fieldChecks': field_results, 'strengthChecks': strengths,
                        'policyChecks': policy_checks, 'actualExtraction': {
                            'profile': analysis.profile, 'unconfirmedFields': sorted(analysis.unconfirmed_fields),
                            'companionHints': analysis.companion_hints, 'fallback': analysis.fallback,
                            'failure': analysis.failure}, 'actual': actual,
                        'verdict': ('REVIEW_REQUIRED' if expected.get('mustNot') else 'PASS')
                        if all(field_results.values()) and all(strengths.values()) and all(policy_checks.values()) else 'FAIL',
                        'manualReviewRequired': expected.get('mustNot', [])})
    correct = sum(sum(r['fieldChecks'].values()) for r in records)
    strengths = [value for r in records for value in r['strengthChecks'].values()]
    missing = [r for r, case in zip(records, dataset['cases']) if case['category'] == '되묻기']
    return {'fieldAccuracy': {'correct': correct, 'total': len(fields) * len(records),
                              'ratio': correct / (len(fields) * len(records))},
            'strengthAccuracy': {'correct': sum(strengths), 'total': len(strengths),
                                 'ratio': sum(strengths) / len(strengths) if strengths else None},
            'missingQuestionCases': {'correct': sum(r['policyChecks']['questionFields'] for r in missing), 'total': len(missing)},
            'questionOverflowCount': sum(len(r['actual']['questions']) > 2 for r in records),
            'cases': records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=('rules', 'gemini'), default='rules')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads((Path(__file__).with_name('cases.json')).read_text(encoding='utf-8'))
    if args.provider == 'gemini':
        from dotenv import load_dotenv
        load_dotenv(ROOT / 'backend/.env')
        key, model = os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')
        if not key or not model:
            parser.error('Set GEMINI_API_KEY and GEMINI_MODEL in backend/.env before live synthetic evaluation.')
        provider = GeminiProvider(key, model)
    else:
        provider, model = UnconfiguredProvider(), 'chat-rule-parser-v1'
    extractor = AIConditionExtractor(AIService(provider, reference_now=datetime.fromisoformat(dataset['referenceNow'])), ChatRuleParser())
    report = asyncio.run(evaluate(dataset, extractor))
    report.update({'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
                   'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                   'datasetVersion': dataset['version'], 'referenceNow': dataset['referenceNow'],
                   'provider': args.provider, 'modelVersion': model, 'syntheticOnly': True,
                   'policyExecution': 'direct-policy-no-http',
                   'fallbackCaseCount': sum(r['actualExtraction']['fallback'] for r in report['cases']),
                   'llmAccuracyMeasured': args.provider == 'gemini' and not any(r['actualExtraction']['fallback'] for r in report['cases']),
                   'datasetStatus': dataset['status'], 'mustNotChecks': 'manual review required; excluded from automatic verdict'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('provider', 'fieldAccuracy', 'strengthAccuracy',
          'missingQuestionCases', 'questionOverflowCount', 'llmAccuracyMeasured')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
