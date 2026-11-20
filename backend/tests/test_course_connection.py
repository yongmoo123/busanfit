"""Connection preparation and fixture-only DB audits; no service activation."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.application.course_connection import prepare_course_connection, CourseConnectionError
from app.application.course_service import CourseService
from app.courses.companion_scoring import load_companion_proposal
from app.courses.fakes import FakeRetriever, FakeTravel
from app.data.db import connect
from app.domain.course import CourseSettings
from app.main import create_app
from test_server_sqlite_integration import stored

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('course_database_run', ROOT / 'evaluation/courses/database_run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def dataset(tmp_path, *, expected='SUCCESS'):
    profile = {
        'area': {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'},
        'timeWindow': {'value': {'startAt': '2026-11-21T10:00:00+09:00',
                                'endAt': '2026-11-21T18:00:00+09:00'}, 'source': 'USER', 'strength': 'HARD'}}
    cases = []
    for index, mode in enumerate((None, 'WHEELCHAIR', 'STROLLER', 'INJURY'), 1):
        values = dict(profile)
        if mode:
            values['mobility'] = {'value': [mode], 'source': 'USER', 'strength': 'HARD'}
        cases.append({'id': f'CS-{index:02d}', 'profile': values, 'expected': {'outcome': expected}})
    cases.append({'id': 'CS-unsupported', 'profile': profile, 'requiresSupport': ['indoorPreference'],
                  'expected': {'outcome': expected}})
    path = tmp_path / 'synthetic-cases.json'
    path.write_text(json.dumps({'version': 'synthetic-fixture', 'cases': cases}), encoding='utf-8')
    return path


def fixture_connection(stored):
    path, places, repository = stored
    travel = FakeTravel()
    return SimpleNamespace(repository=repository,
        service=CourseService(FakeRetriever(places), travel, repository), settings=CourseSettings(),
        retrieval_settings=SimpleNamespace(area_centers={'HAEUNDAE': (35.16, 129.16)}, excluded_place_ids=frozenset()),
        weights_version='synthetic-fixture')


def test_missing_db_and_provider_never_become_fake_dependencies(tmp_path):
    with pytest.raises(CourseConnectionError, match='COMP-06'):
        prepare_course_connection(tmp_path / 'missing.sqlite3', travel_provider=None)
    with pytest.raises(CourseConnectionError, match='existing SQLite'):
        prepare_course_connection(tmp_path / 'missing.sqlite3', travel_provider=FakeTravel())
    assert not (tmp_path / 'missing.sqlite3').exists()


def test_approved_only_rejects_a_coherent_draft(tmp_path):
    draft = json.loads((ROOT / 'config/companion-weights.proposal.json').read_text(encoding='utf-8'))
    draft.update(status='PROPOSAL', pmApproved=False)
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(draft), encoding='utf-8')
    load_companion_proposal(path)  # Draft review remains supported.
    with pytest.raises(ValueError, match='approved companion'):
        load_companion_proposal(path, approved_only=True)


def test_read_only_db_mode_cannot_modify_data(stored):
    with connect(stored[0], read_only=True) as conn:
        import sqlite3
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('DELETE FROM places')
    conn.close()
    with pytest.raises(ValueError):
        connect(stored[0], create=True, read_only=True)


def test_database_runner_audits_four_fixture_modes_without_leaking_sessions(stored, tmp_path):
    path = dataset(tmp_path)
    before = path.read_bytes()
    report = runner.evaluate_database(fixture_connection(stored), path, synthetic=True)
    assert report['syntheticOnly'] and not report['realDataVerified'] and not report['realTravelVerified']
    assert not report['acceptanceComplete'] and report['automatedChecksPassed']
    assert report['executedScenarios'] == 4 and report['excludedScenarios'] == 1
    assert report['hardViolations'] == report['missingPlaceIds'] == 0
    assert report['dbSha256'] == runner.file_sha256(stored[0])
    assert report['within15SecondsRatio'] == 1 and report['performanceTargetMet']
    assert path.read_bytes() == before
    text = json.dumps(report)
    assert 'sessionId' not in text and 'profileRevision' not in text and 'sampleResponse' not in text


@pytest.mark.parametrize('allowed', [False, True])
def test_insufficient_is_only_correct_when_case_allows_it(stored, tmp_path, allowed):
    connection = fixture_connection(stored)
    connection.service.retriever = FakeRetriever([])
    report = runner.evaluate_database(connection,
        dataset(tmp_path, expected='SUCCESS_OR_INSUFFICIENT' if allowed else 'SUCCESS'), synthetic=True)
    assert report['automatedChecksPassed'] is allowed
    assert report['hardViolations'] == (0 if allowed else None)
    assert [r['state'] for r in report['scenarioResults'][:4]] == (['PASS'] if allowed else ['FAIL']) * 4


@pytest.mark.parametrize('fault', ['missing-id', 'duty-free', 'saved-profile', 'http-error'])
def test_runner_rejects_bad_success_and_http_errors(stored, tmp_path, fault):
    connection = fixture_connection(stored)
    path = dataset(tmp_path)
    if fault == 'duty-free':
        connection.retrieval_settings.excluded_place_ids = frozenset(p.id for p in stored[1])
    elif fault == 'saved-profile':
        data = json.loads(path.read_text())
        for case in data['cases']:
            case['expected']['savedProfile'] = {'mobility': {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}}
        path.write_text(json.dumps(data), encoding='utf-8')
    elif fault == 'http-error':
        def broken(p): raise RuntimeError('synthetic private detail')
        connection.service.retriever.retrieve = broken
    else:
        original = connection.service.generate
        def missing(*args):
            result = original(*args)
            result.course.items[0].place.id = 'synthetic:absent'
            return result
        connection.service.generate = missing
    report = runner.evaluate_database(connection, path, synthetic=True)
    assert not report['automatedChecksPassed'] and report['hardViolations'] is None
    assert 'synthetic private detail' not in json.dumps(report)


@pytest.mark.parametrize('fault', ['duplicate', 'empty', 'unknown-outcome', 'unknown-profile', 'bad-expected'])
def test_cases_are_validated_before_execution(tmp_path, fault):
    path = dataset(tmp_path)
    data = json.loads(path.read_text())
    if fault == 'duplicate': data['cases'][1]['id'] = data['cases'][0]['id']
    if fault == 'empty': data['cases'] = []
    if fault == 'unknown-outcome': data['cases'][0]['expected']['outcome'] = 'WHATEVER'
    if fault == 'unknown-profile': data['cases'][0]['profile']['typo'] = {}
    if fault == 'bad-expected': data['cases'][0]['expected'] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): runner.load_cases(path)


def test_no_fake_or_implicit_travel_factory():
    for value in ('', 'app.courses.fakes:FakeTravel', 'module-only'):
        with pytest.raises(ValueError): runner.load_travel_provider(value)


def test_missing_pr65_is_an_explicit_dependency_error(stored):
    if importlib.util.find_spec('app.retrieval') is not None:
        pytest.skip('dependency is present in this combined validation tree')
    with pytest.raises(CourseConnectionError, match='PR #65'):
        prepare_course_connection(stored[0], travel_provider=FakeTravel())


def test_cli_refuses_real_mode_without_comp06_and_writes_no_success_report(tmp_path):
    import os
    import subprocess
    import sys
    output = tmp_path / 'not-a-real-result.json'
    env = {key: value for key, value in os.environ.items() if key not in ('GEMINI_API_KEY', 'GEMINI_MODEL')}
    run = subprocess.run([sys.executable, 'evaluation/courses/run.py', '--mode', 'real',
        '--output', str(output)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert run.returncode == 2
    assert 'prerequisites failed' in run.stderr and not output.exists()


def test_preparation_keeps_ordinary_app_closed(stored):
    with TestClient(create_app()) as client:
        caps = client.post('/api/sessions', json={}).json()['capabilities']
        assert caps['supportedAreas'] == [] and not caps['supportsUnknownAccessibilityInclusion']


@pytest.mark.parametrize('radius', [1500, 2000])
def test_actual_pr65_retrieval_and_shared_radius_with_fixture_db(stored, radius):
    settings_module = pytest.importorskip('app.retrieval.settings', reason='PR #65 not yet in develop')
    settings = settings_module.RetrievalSettings({'HAEUNDAE': (35.16, 129.16)}, radius)
    connection = prepare_course_connection(stored[0], travel_provider=FakeTravel(), retrieval_settings=settings)
    assert connection.settings.radius_meters == radius
    assert connection.service.scheduler.settings == connection.settings
    assert connection.service.validator.settings == connection.settings
    assert connection.repository.read_only
    assert connection.service.scheduler.scorer.proposal.version == connection.weights_version
    assert runner.evaluate_database(connection, dataset(stored[0].parent), synthetic=True)['automatedChecksPassed']


@pytest.mark.parametrize('radius,expected', [(1500, 'INSUFFICIENT_PLACES'), (2000, 'SUCCESS')])
def test_search_and_validator_agree_for_fixture_places_between_1500_and_2000_m(stored, radius, expected):
    settings_module = pytest.importorskip('app.retrieval.settings', reason='PR #65 not yet in develop')
    with connect(stored[0]) as conn:
        conn.execute('UPDATE places SET latitude = 35.175, longitude = 129.16')
    conn.close()
    settings = settings_module.RetrievalSettings({'HAEUNDAE': (35.16, 129.16)}, radius)
    connection = prepare_course_connection(stored[0], travel_provider=FakeTravel(), retrieval_settings=settings)
    report = runner.evaluate_database(connection,
        dataset(stored[0].parent, expected='SUCCESS_OR_INSUFFICIENT'), synthetic=True)
    assert report['automatedChecksPassed']
    assert all(r['outcome'] == expected for r in report['scenarioResults'][:4])
