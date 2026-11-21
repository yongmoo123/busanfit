"""Case-driven, in-process DB evaluation. No network, LLM calls or app activation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import subprocess
from time import perf_counter

from fastapi.testclient import TestClient
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor, blank_profile
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.data.geo import haversine_m
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
# PR #53 CS-01~10 / DEC-001·023: the evaluation scope is fixed,
# independently of configurable search/validation settings used by the app.
EVALUATION_RADIUS_METERS = 1500
EVALUATION_CENTER = (35.159084, 129.160279)


def validate_evaluation_scope(connection):
    settings = connection.retrieval_settings
    if (connection.settings.radius_meters != EVALUATION_RADIUS_METERS
            or settings.radius_m != EVALUATION_RADIUS_METERS):
        raise ValueError('official course evaluation requires a 1500m radius')
    if settings.area_centers.get('HAEUNDAE') != EVALUATION_CENTER:
        raise ValueError('official course evaluation requires the DEC-023 HAEUNDAE center')


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_cases(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    cases = data.get('cases') if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError('nonempty cases list required (PR #53)')
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id'] or case['id'] in ids:
            raise ValueError('unique case IDs required')
        ids.add(case['id'])
        expected = case.get('expected')
        if (not isinstance(case.get('profile'), dict)
                or not set(case['profile']) <= set(blank_profile())
                or not isinstance(expected, dict)
                or expected.get('outcome') not in ('SUCCESS', 'SUCCESS_OR_INSUFFICIENT')):
            raise ValueError('invalid case profile or expected outcome')
        if (not isinstance(expected.get('savedProfile', {}), dict)
                or not isinstance(expected.get('extraChecks', []), list)
                or not all(isinstance(value, str) for value in expected.get('extraChecks', []))):
            raise ValueError('invalid expected profile/manual checks')
        required = case.get('requiresSupport', [])
        if not isinstance(required, list) or not all(field in blank_profile() for field in required):
            raise ValueError('invalid requiresSupport')
    return data


def load_travel_provider(spec):
    """Explicit caller-selected zero-argument factory implementing agreed COMP-06 port."""
    module, separator, name = spec.partition(':')
    if not separator or not module or not name or module.startswith('app.courses.fakes'):
        raise ValueError('supply the agreed COMP-06 module:factory, not FakeTravel')
    provider = getattr(importlib.import_module(module), name)()
    if not callable(getattr(provider, 'estimate', None)):
        raise ValueError('travel factory must return TravelTimeProvider')
    return provider


def evaluate_database(connection, cases_path, *, synthetic=False):
    """Use synthetic=True for fixture tests; never write results into input cases.

    The HTTP app lives only inside TestClient. Ordinary app/main is untouched.
    Results omit profiles, session tokens and raw response bodies.
    """
    if not __debug__:
        raise ValueError('contract checks require Python without -O')
    validate_evaluation_scope(connection)
    dataset = load_cases(cases_path)
    cases_sha = file_sha256(cases_path)
    db_path = connection.repository.path
    before = file_sha256(db_path)
    contract = runpy.run_path(str(ROOT / 'contracts/validate_contract.py'))
    audit = runpy.run_path(str(Path(__file__).with_name('audit.py')))['audit_response']
    app = create_app(course_service=connection.service,
        extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()),
        profile_support=ProfileSupport(True, frozenset(INITIAL_FIELDS), True))
    results = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for case in dataset['cases']:
            result = {'id': case['id'], 'state': 'FAIL', 'responseMs': None,
                      'hardViolations': None, 'missingPlaceIds': None,
                      'manualChecksPending': case['expected'].get('extraChecks', [])}
            session = client.post('/api/sessions', json={})
            if session.status_code != 201:
                raise RuntimeError('session setup failed')
            session = session.json()
            sid = session['sessionId']
            try:
                unsupported = set(case.get('requiresSupport', [])) - set(session['capabilities']['supportedProfileFields'])
                if unsupported:
                    result.update(state='EXCLUDED', unsupportedFields=sorted(unsupported))
                    results.append(result)
                    continue
                profile = blank_profile() | deepcopy(case['profile'])
                saved = client.put(f'/api/sessions/{sid}/profile',
                    json={'profile': profile, 'expectedProfileRevision': 0})
                if saved.status_code != 200 or saved.json()['status'] != 'READY':
                    result['failure'] = 'PROFILE_NOT_READY'
                    results.append(result)
                    continue
                saved = saved.json()
                revision, profile = saved['profileRevision'], saved['profile']
                started = perf_counter()
                response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': revision})
                result['responseMs'] = (perf_counter() - started) * 1000
                if response.status_code != 200:
                    result.update(failure='COURSE_HTTP_ERROR', httpStatus=response.status_code)
                    results.append(result)
                    continue
                body = response.json()
                try:
                    contract['check'](body, contract['schemas']['CourseResponse'])
                    injury_warning_count = sum(w['code'] == 'INJURY_RULES' for w in body['warnings'])
                    if injury_warning_count != int('INJURY' in (profile['mobility']['value'] or ())):
                        raise AssertionError('injury_rule_warning')
                    for field, expected in case['expected'].get('savedProfile', {}).items():
                        if profile.get(field) != expected:
                            raise AssertionError('saved_profile')
                    if body['status'] == 'SUCCESS':
                        center = connection.retrieval_settings.area_centers[profile['area']['value']]
                        distances = {}
                        for item in body['course']['items']:
                            place = connection.repository.get_place(item['place']['id'])
                            if place is None:
                                raise AssertionError('missing_repository_id')
                            if place.id in connection.retrieval_settings.excluded_place_ids:
                                raise AssertionError('duty_free_exclusion')
                            if place.open_hours.parsed is None:
                                raise AssertionError('unknown_open_hours')
                            distances[place.id] = haversine_m(*center, place.latitude, place.longitude)
                        audit(body, profile, revision, connection.repository,
                              connection.service.travel_provider, distances,
                              radius_meters=EVALUATION_RADIUS_METERS)
                    elif case['expected']['outcome'] != 'SUCCESS_OR_INSUFFICIENT' or body['course'] is not None:
                        raise AssertionError('unexpected_insufficient')
                    result.update(state='PASS', outcome=body['status'], hardViolations=0, missingPlaceIds=0,
                                  excludedUnknown=body['excludedUnknown'],
                                  warningCodes=sorted({w['code'] for w in body['warnings']}))
                except (AssertionError, ValueError, KeyError, TypeError):
                    # Do not serialize exception text, profiles or source raw data.
                    result['failure'] = 'RESPONSE_AUDIT_FAILED'
                results.append(result)
            finally:
                client.delete(f'/api/sessions/{sid}')
    if file_sha256(db_path) != before:
        raise RuntimeError('database changed during evaluation; discard this run')
    if file_sha256(cases_path) != cases_sha:
        raise RuntimeError('cases changed during evaluation; discard this run')
    executed = [r for r in results if r['state'] != 'EXCLUDED']
    passed = bool(executed) and all(r['state'] == 'PASS' for r in executed)
    within_target = sum(r['responseMs'] is not None and r['responseMs'] <= 15000 for r in executed)
    ratio = within_target / len(executed) if executed else None
    return {'syntheticOnly': synthetic, 'realDataVerified': False, 'realTravelVerified': False,
            'acceptanceComplete': False, 'runDate': datetime.now(timezone(timedelta(hours=9))).isoformat(),
            'codeRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'workingTreeModified': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
            'dbSha256': before, 'casesSha256': cases_sha, 'casesVersion': dataset.get('version'),
            'radiusMeters': connection.settings.radius_meters, 'weightsVersion': connection.weights_version,
            'evaluationCenter': {'latitude': EVALUATION_CENTER[0], 'longitude': EVALUATION_CENTER[1]},
            'travelProvider': type(connection.service.travel_provider).__module__ + ':' + type(connection.service.travel_provider).__qualname__,
            'scenarioResults': results, 'executedScenarios': len(executed),
            'excludedScenarios': len(results) - len(executed), 'automatedChecksPassed': passed,
            'hardViolations': 0 if passed else None, 'missingPlaceIds': 0 if passed else None,
            'within15SecondsRatio': ratio, 'performanceTargetMet': ratio is not None and ratio >= 0.9,
            'manualReviewRequired': True}


def run_database(args):
    from app.application.course_connection import prepare_course_connection
    from app.data.db import get_db_path
    if not args.travel_provider:
        raise ValueError('--travel-provider module:factory is required; COMP-06 has no fallback')
    path = get_db_path()
    if args.output.resolve() == path.resolve() or args.output.resolve() == args.cases.resolve():
        raise ValueError('output must not overwrite the DB or cases')
    if args.expected_db_sha256 and file_sha256(path) != args.expected_db_sha256.lower():
        raise ValueError('DB SHA-256 does not match the shared file')
    load_cases(args.cases)  # Missing #53 is a dependency error, never synthetic fallback.
    connection = prepare_course_connection(path, travel_provider=load_travel_provider(args.travel_provider))
    report = evaluate_database(connection, args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('syntheticOnly', 'executedScenarios', 'excludedScenarios',
        'automatedChecksPassed', 'performanceTargetMet')}, ensure_ascii=False))
    return 0 if report['automatedChecksPassed'] and report['performanceTargetMet'] else 1
