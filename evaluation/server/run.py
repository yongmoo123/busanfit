"""One-command reproducible backend evidence; no live API/model or UI claims."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def run_check(name, arguments):
    result = subprocess.run([sys.executable, *arguments], cwd=ROOT, text=True,
        encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    # Persist only aggregate counters, never failure tracebacks or HTTP/session logs.
    counts = re.findall(r'(\d+) passed', result.stdout)
    return {'check': name, 'passed': result.returncode == 0,
            **({'pytestPassed': int(counts[-1])} if counts else {})}


def run():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    modified = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    checks = [run_check('pytest', ['-m', 'pytest', '-q']),
              run_check('contract', ['contracts/validate_contract.py']),
              run_check('source-sync', ['contracts/validate_source_sync.py'])]
    diff = subprocess.run(['git', 'diff', 'HEAD', '--check'], cwd=ROOT, capture_output=True, timeout=30)
    checks.append({'check': 'diff-check', 'passed': diff.returncode == 0})
    suites = [('extraction-rules-reference', 'extraction/run.py', ['--provider', 'rules']),
              ('courses-synthetic-40', 'courses/run.py', []),
              ('explanations-synthetic-8', 'explanations/run.py', []),
              ('suggestions-synthetic-4', 'suggestions/run.py', []),
              ('companions-proposal-synthetic-12', 'companions/run.py', [])]
    suite_summaries = []
    with TemporaryDirectory(prefix='busanfit-server-acceptance-') as directory:
        for name, script, extra in suites:
            output = Path(directory) / (name + '.json')
            checked = run_check(name, ['evaluation/' + script, *extra, '--output', str(output)])
            checks.append(checked)
            if checked['passed']:
                data = json.loads(output.read_text(encoding='utf-8'))
                summary = {'suite': name, 'syntheticOnly': data.get('syntheticOnly', False)}
                for key in ('fieldAccuracy', 'strengthAccuracy', 'missingQuestionCases', 'questionOverflowCount',
                            'llmAccuracyMeasured', 'totalRequests', 'hardViolations', 'maxResponseMs', 'httpScenarios'):
                    if key in data: summary[key] = data[key]
                if 'scenarioResults' in data: summary['scenarios'] = len(data['scenarioResults'])
                elif 'scenarios' in data: summary['scenarios'] = len(data['scenarios'])
                suite_summaries.append(summary)
    screenshots = [ROOT / 'docs/evidence/issue20' / name for name in ('chat-desktop.jpg', 'chat-mobile.jpg', 'chat-503.jpg')]
    return {'verificationScope': 'OFFLINE_SYNTHETIC_ROWS_WITH_REAL_SQLITE',
        'codeRevision': revision, 'workingTreeModified': modified,
        'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'allChecksPassed': all(check['passed'] for check in checks), 'checks': checks, 'suites': suite_summaries,
        'sqliteImplementationIntegrated': True, 'sqliteRowsSyntheticOnly': True,
        'realHaeundaeDataVerified': False, 'realRetrievalAndTravelVerified': False,
        'liveLlmStatus': 'DEFERRED_BY_USER', 'frontendStatus': 'HANDOFF_TO_FRONTEND_OWNER',
        'companionWeightsPmApproved': False, 'companionWeightsOrdinaryActivated': False,
        'existingVirtualChatScreenshotsPresent': all(path.is_file() for path in screenshots)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'allChecksPassed': report['allChecksPassed'], 'checks': report['checks'],
                      'liveLlmStatus': report['liveLlmStatus'], 'frontendStatus': report['frontendStatus']}, ensure_ascii=False))
    if not report['allChecksPassed']: raise SystemExit(1)
