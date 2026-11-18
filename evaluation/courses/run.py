"""HTTP-level synthetic four-scenario audit and latency measurements, not real data."""
import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from app.application.course_service import CourseService
from app.application.extraction import blank_profile
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.domain.place import OpenHoursRecord
from app.main import create_app
from audit import audit_response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error('Contract assertions require Python without -O.')
    contract = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))
    places = [synthetic_place(i) for i in range(1, 9)]
    places[5] = replace(places[5], open_hours=OpenHoursRecord(None, None))
    places[6] = replace(places[6], accessibility=replace(places[6].accessibility, wheelchair=None))
    places[7] = replace(places[7], accessibility=replace(places[7].accessibility, wheelchair=False, stroller=None))
    repository, travel = FakeRepository(places), FakeTravel()
    service = CourseService(FakeRetriever(places), travel, repository)
    support = ProfileSupport(True, frozenset(INITIAL_FIELDS), True)
    report = {'syntheticOnly': True, 'realDataVerified': False, 'realTravelVerified': False,
              'referenceDate': '2026-11-13', 'scenarioResults': [], 'negativeControls': []}
    durations = []
    last_body = last_profile = None
    with TestClient(create_app(profile_support=support, course_service=service)) as client:
        for mode in ('GENERAL', 'WHEELCHAIR', 'STROLLER', 'INJURY'):
            sid = client.post('/api/sessions', json={}).json()['sessionId']
            profile = blank_profile()
            profile['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
            profile['timeWindow'] = {'value': {'startAt': '2026-11-13T09:00:00+09:00', 'endAt': '2026-11-13T20:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}
            if mode != 'GENERAL':
                profile['mobility'] = {'value': [mode], 'source': 'USER', 'strength': 'HARD'}
            saved = client.put(f'/api/sessions/{sid}/profile', json={'expectedProfileRevision': 0, 'profile': profile})
            if saved.status_code != 200:
                raise RuntimeError('Synthetic profile setup failed.')
            profile = saved.json()['profile']
            samples = []
            for _ in range(10):
                started = perf_counter()
                response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
                samples.append((perf_counter() - started) * 1000)
                if response.status_code != 200:
                    raise RuntimeError('Synthetic course HTTP request failed.')
                body = response.json()
                contract['check'](body, contract['schemas']['CourseResponse'])
                audited = audit_response(body, profile, 1, repository, travel, {p.id: 100 for p in places})
            durations += samples
            report['scenarioResults'].append({'id': mode, **audited, 'httpRequests': 10,
                'latencyMs': {'min': min(samples), 'max': max(samples), 'mean': sum(samples) / len(samples)},
                'excludedUnknown': body['excludedUnknown'], 'sampleResponse': body})
            last_body, last_profile = body, profile
    # An independent checker must reject corrupted success responses as well.
    from copy import deepcopy
    for name in ('unknown-place', 'outside-window', 'injury-long-leg', 'unverified-hard', 'missing-source'):
        corrupted = deepcopy(last_body)
        if name == 'unknown-place':
            corrupted['course']['items'][0]['place']['id'] = 'synthetic:missing'
        elif name == 'outside-window':
            corrupted['course']['items'][0]['startAt'] = '2026-11-13T08:00:00+09:00'
        elif name == 'injury-long-leg':
            corrupted['course']['legs'][0]['minutes'] = 11
        elif name == 'unverified-hard':
            corrupted['course']['validation']['unverifiedFields'].append('mobility.wheelchair')
        else:
            corrupted['course']['sources'] = []
        try:
            audit_response(corrupted, last_profile, 1, repository, travel, {p.id: 100 for p in places})
        except AssertionError:
            report['negativeControls'].append({'id': name, 'rejected': True})
        else:
            raise RuntimeError('Independent checker accepted a negative control.')
    report.update({'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'totalRequests': len(durations), 'hardViolations': 0,
        'maxResponseMs': max(durations), 'synthetic15SecondTargetMet': max(durations) <= 15000})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('syntheticOnly', 'totalRequests', 'hardViolations', 'maxResponseMs', 'synthetic15SecondTargetMet')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
