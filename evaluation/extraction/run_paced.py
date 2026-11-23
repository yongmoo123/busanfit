"""Paced wrapper around evaluation/extraction/run.py (DEC-030: space requests on free tier).

Usage: python evaluation/extraction/run_paced.py <output.json> [delay_seconds=6]

Adds a fixed delay between cases and records per-case extraction latency.
Does not modify the repository runner. Never prints or stores the API key.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'evaluation' / 'extraction'))
sys.path.insert(0, str(ROOT / 'backend'))
import run  # noqa: E402

DELAY = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
OUT = Path(sys.argv[1])

causes = []


class CauseHandler(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if 'ai_attempt' in msg or 'attempt' in msg:
            causes.append(msg[:200])


logging.getLogger().addHandler(CauseHandler())
logging.getLogger().setLevel(logging.INFO)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'backend/.env')
    key, model = os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')
    if not key or not model:
        raise SystemExit('missing GEMINI settings')
    dataset = json.loads((ROOT / 'evaluation/extraction/cases.json').read_text(encoding='utf-8'))
    extractor = run.AIConditionExtractor(
        run.AIService(run.GeminiProvider(key, model), reference_now=datetime.fromisoformat(dataset['referenceNow'])),
        run.ChatRuleParser())
    latencies = []
    original = extractor.extract
    first = [True]

    async def paced(message):
        if not first[0]:
            await asyncio.sleep(DELAY)
        first[0] = False
        start = time.perf_counter()
        result = await original(message)
        latencies.append(round((time.perf_counter() - start) * 1000, 1))
        return result

    extractor.extract = paced
    report = asyncio.run(run.evaluate(dataset, extractor))
    for record, ms in zip(report['cases'], latencies):
        record['extractionMs'] = ms
    fb = [r for r in report['cases'] if r['actualExtraction']['fallback']]
    llm_ms = sorted(r['extractionMs'] for r in report['cases'] if not r['actualExtraction']['fallback'])
    report.update({
        'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'datasetVersion': dataset['version'], 'referenceNow': dataset['referenceNow'],
        'provider': 'gemini', 'modelVersion': model, 'syntheticOnly': True,
        'policyExecution': 'direct-policy-no-http', 'runner': 'paced wrapper (delay %.1fs between cases)' % DELAY,
        'fallbackCaseCount': len(fb), 'fallbackCases': [r['id'] for r in fb],
        'llmAccuracyMeasured': not fb,
        'latency': {'llmCases': len(llm_ms), 'maxMs': llm_ms[-1] if llm_ms else None,
                    'meanMs': round(sum(llm_ms) / len(llm_ms), 1) if llm_ms else None,
                    'within5s': sum(ms <= 5000 for ms in llm_ms)},
        'attemptLogSample': causes[-20:],
        'datasetStatus': dataset['status'],
        'mustNotChecks': 'manual review required; excluded from automatic verdict'})
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('fieldAccuracy', 'strengthAccuracy', 'missingQuestionCases',
                                             'questionOverflowCount', 'fallbackCaseCount', 'fallbackCases',
                                             'llmAccuracyMeasured', 'latency')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
