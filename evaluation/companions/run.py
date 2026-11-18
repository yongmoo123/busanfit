"""Draft-only same-candidate comparison; no real DB/model or policy approval."""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from app.application.extraction import blank_profile
from app.companion_demo import create_demo
from app.courses.companion_scoring import load_companion_proposal
from app.courses.scheduler import CourseScheduler, default_score

contract = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))
audit = runpy.run_path(str(ROOT / 'evaluation/courses/audit.py'))['audit_response']


def run():
    proposal = load_companion_proposal()
    records = []
    for kind in ('COUPLE', 'FAMILY', 'FRIENDS', 'SOLO', 'OTHER', None):
        pair = []
        for proposed in (False, True):
            app = create_demo(proposal=proposed)
            with TestClient(app) as client:
                sid = client.post('/api/sessions', json={}).json()['sessionId']
                profile = blank_profile()
                profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
                profile['timeWindow'] = {'value': {'startAt': '2026-11-17T13:00:00+09:00',
                    'endAt': '2026-11-17T15:15:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
                if kind:
                    profile['companions'] = {'value': {'type': kind, 'count': 1 if kind == 'SOLO' else 2 if kind == 'COUPLE' else 3,
                        'hasInfant': False}, 'source': 'USER', 'strength': 'SOFT'}
                saved = client.put('/api/sessions/' + sid + '/profile', json={'profile': profile, 'expectedProfileRevision': 0})
                assert saved.status_code == 200
                actual_profile = saved.json()['profile']
                response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
                assert response.status_code == 200
                body = response.json()
                contract['check'](body, contract['schemas']['CourseResponse'])
                assert body['status'] == 'SUCCESS'
                service = app.state.course_service
                audited = audit(body, actual_profile, 1, service.repository, service.travel_provider,
                    {key: 100 for key in service.repository.places}, allowed_reason_methods=('LLM', 'TEMPLATE'))
                from app.api.profile_models import Profile
                typed = Profile.model_validate(actual_profile)
                scorer = service.scheduler.scorer
                ranks = sorted(service.repository.places.values(), key=lambda p: (-scorer(p, typed), p.id))
                pair.append({'scorer': 'PROPOSAL' if proposed else 'BASELINE',
                    'selectedCategories': [i['place']['category'] for i in body['course']['items']],
                    'ranking': [{'placeId': p.id, 'category': p.category, 'score': scorer(p, typed)} for p in ranks],
                    'hardViolations': audited['hardViolations'], 'missingPlaceIds': audited['missingPlaceIds']})
                assert app.state.sessions.check_current(sid, 1).profile == actual_profile
        changed = pair[0]['selectedCategories'] != pair[1]['selectedCategories']
        assert changed == (kind in ('COUPLE', 'FAMILY', 'FRIENDS'))
        records.append({'companionType': kind or 'UNSET', 'changed': changed, 'comparisons': pair})
    return {'syntheticOnly': True, 'proposalStatus': 'PROPOSAL', 'pmApproved': False,
        'normalPathActivated': False, 'ordinaryScorerUnchanged': CourseScheduler().scorer is default_score,
        'realDbVerified': False, 'realLlmVerified': False, 'proposalVersion': proposal.version,
        'proposalSha256': sha256((ROOT / 'config/companion-weights.proposal.json').read_bytes()).hexdigest(),
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(), 'httpScenarios': 12, 'scenarios': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: 12 synthetic HTTP scenarios; draft group differences, neutral baselines, zero hard violations; not approved/activated.')
