"""Synthetic HTTP acceptance, not real DB/model accuracy or performance evidence."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from app.application.extraction import blank_profile
from app.explanation_demo import create_demo

audit = runpy.run_path(str(ROOT / 'evaluation/courses/audit.py'))['audit_response']
contract = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))


def run():
    records = []
    for fallback in (False, True):
        for mobility in (None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']):
            app = create_demo(fallback=fallback)
            with TestClient(app) as client:
                session = client.post('/api/sessions', json={}).json()
                profile = blank_profile()
                profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
                profile['timeWindow'] = {'value': {'startAt': '2026-11-16T13:00:00+09:00',
                    'endAt': '2026-11-16T18:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
                if mobility: profile['mobility'] = {'value': mobility, 'source': 'USER', 'strength': 'HARD'}
                saved = client.put('/api/sessions/' + session['sessionId'] + '/profile',
                    json={'profile': profile, 'expectedProfileRevision': 0})
                assert saved.status_code == 200
                started = perf_counter()
                response = client.post('/api/courses', json={'sessionId': session['sessionId'], 'profileRevision': 1})
                elapsed = (perf_counter() - started) * 1000
                assert response.status_code == 200
                body = response.json()
                contract['check'](body, contract['schemas']['CourseResponse'])
                assert body['status'] == 'SUCCESS'
                course = body['course']
                # The existing independent hard checker does not call the engine validator.
                audited = audit(body, saved.json()['profile'], 1, app.state.place_repository,
                    app.state.course_service.travel_provider,
                    {key: 100 for key in app.state.place_repository.places}, allowed_reason_methods=('LLM', 'TEMPLATE'))
                for item in course['items']:
                    detail = client.get('/api/places/' + item['place']['id'])
                    assert detail.status_code == 200
                    contract['check'](detail.json(), contract['schemas']['PlaceResponse'])
                    assert detail.json()['place'] == item['place']
                    assert item['reasonMethod'] == ('TEMPLATE' if fallback else 'LLM')
                    assert 1 <= item['reason'].count('요.') <= 2
                    assert all(s in course['sources'] for s in detail.json()['sources'])
                assert any(w['code'] == 'AI_FALLBACK' for w in body['warnings']) == fallback
                unknown = client.get('/api/places/synthetic:unknown-detail').json()
                assert unknown['place']['openHours'] == {'status': 'UNKNOWN', 'description': None}
                assert unknown['place']['accessibility']['grade'] == 'UNKNOWN'
                assert client.get('/api/places/synthetic:absent').status_code == 404
                records.append({'mode': (mobility or ['GENERAL'])[0], 'provider': 'unconfigured' if fallback else 'synthetic-selector',
                    'status': body['status'], 'items': len(course['items']), 'reasonMethod': 'TEMPLATE' if fallback else 'LLM',
                    'hardViolations': audited['hardViolations'], 'detailMatchesCourse': True, 'unknownDetailPreserved': True,
                    'elapsedMs': round(elapsed, 3)})
    return {'syntheticOnly': True, 'realDbVerified': False, 'realLlmVerified': False,
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(), 'scenarios': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"PASS: {len(report['scenarios'])} synthetic HTTP scenarios; no real DB/model calls.")
