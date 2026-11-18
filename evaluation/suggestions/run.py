"""Synthetic backend acceptance: suggestion -> card save -> regenerate.

This is HTTP/ASGI verification, not a frontend click test or real-data acceptance.
No session identifiers, user messages or raw health inputs are written to reports.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from app.application.extraction import blank_profile
from app.explanation_demo import create_demo

contract = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))
audit = runpy.run_path(str(ROOT / 'evaluation/courses/audit.py'))['audit_response']


def scenario(name):
    app = create_demo()
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        profile = blank_profile()
        profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
        profile['timeWindow'] = {'value': {'startAt': '2026-11-17T13:00:00+09:00',
            'endAt': '2026-11-17T18:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
        if name in ('confirm-mobility', 'remove-mobility'):
            profile['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': True},
                                     'source': 'USER', 'strength': 'SOFT'}
        saved = client.put('/api/sessions/' + sid + '/profile',
            json={'profile': profile, 'expectedProfileRevision': 0})
        assert saved.status_code == 200
        profile = saved.json()['profile']
        if name == 'insufficient':
            app.state.course_service.retriever.places = app.state.course_service.retriever.places[:1]

        def generate(revision, actual_profile):
            response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': revision})
            assert response.status_code == 200
            body = response.json()
            contract['check'](body, contract['schemas']['CourseResponse'])
            links = body['suggestions']
            assert len(links) <= 3 and len({s['field'] for s in links}) == len(links)
            for suggestion in links:
                assert suggestion['type'] == 'EDIT_PROFILE'
                assert actual_profile[suggestion['field']]['source'] == 'DEFAULT'
            if body['course'] is not None:
                audited = audit(body, actual_profile, revision, app.state.place_repository,
                    app.state.course_service.travel_provider,
                    {key: 100 for key in app.state.place_repository.places}, allowed_reason_methods=('LLM', 'TEMPLATE'))
                assert audited['hardViolations'] == 0
            else:
                assert links == []
            assert app.state.sessions.check_current(sid, revision).profile == actual_profile
            return body

        before = generate(1, profile)
        before_fields = [s['field'] for s in before['suggestions']]
        if name == 'insufficient':
            assert before['status'] == 'INSUFFICIENT_PLACES'
            return {'id': name, 'beforeFields': [], 'afterFields': [], 'status': before['status'],
                    'hardViolations': 0, 'editRequired': False}
        assert before_fields == (['transport'] if name == 'confirm-transport' else ['transport', 'mobility'])
        edited = deepcopy(profile)
        target = 'transport' if name == 'confirm-transport' else 'mobility'
        edited[target]['source'] = 'USER'
        if name == 'remove-mobility': edited[target]['value'] = []
        updated = client.put('/api/sessions/' + sid + '/profile',
            json={'profile': edited, 'expectedProfileRevision': 1})
        assert updated.status_code == 200 and updated.json()['profileRevision'] == 2
        assert client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1}).status_code == 409
        after = generate(2, updated.json()['profile'])
        after_fields = [s['field'] for s in after['suggestions']]
        assert after_fields == ([] if target == 'transport' else ['transport'])
        assert after['course']['profileRevision'] == 2
        return {'id': name, 'beforeFields': before_fields, 'afterFields': after_fields,
                'status': after['status'], 'hardViolations': 0, 'newRevision': 2,
                'staleRevisionRejected': True, 'editRequired': True}


def run():
    return {'syntheticOnly': True, 'frontendVerified': False, 'realDbVerified': False, 'realLlmVerified': False,
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'scenarios': [scenario(name) for name in ('confirm-transport', 'confirm-mobility', 'remove-mobility', 'insufficient')]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: 4 synthetic backend suggestion/save/regeneration scenarios; no real DB/model calls.')
