"""Ordinary startup composition with actual adapters and explicitly synthetic DB rows."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.api.profile_models import Profile
from app.courses.companion_scoring import ProposalCompanionScorer
from app.courses.fakes import synthetic_place
from app.data.repository import RepositoryError
from app.main import app as ordinary_app, create_app, create_runtime_app
from app.travel.walking import WalkingTravelTimeProvider
from test_courses import ready, CONTRACT
from test_server_sqlite_integration import stored


@pytest.mark.parametrize('mobility', [None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']])
def test_runtime_entry_connects_actual_adapters_course_and_detail(stored, monkeypatch, mobility):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    monkeypatch.delenv('BUSANFIT_WALK_RADIUS_M', raising=False)
    before = hashlib.sha256(stored[0].read_bytes()).hexdigest()
    with TestClient(ordinary_app) as client:
        connection = ordinary_app.state.course_connection
        service = ordinary_app.state.course_service
        assert service is connection.service and connection.repository.read_only
        assert isinstance(service.travel_provider, WalkingTravelTimeProvider)
        assert isinstance(service.scheduler.scorer, ProposalCompanionScorer)
        assert service.settings.radius_meters == service.validator.settings.radius_meters == 1500
        session = client.post('/api/sessions', json={}).json()
        caps = session['capabilities']
        assert caps['supportedAreas'] == ['HAEUNDAE'] and caps['supportedTransports'] == ['WALK']
        assert set(caps['supportedProfileFields']) == {'area','timeWindow','transport','mobility','companions','excludedCategories'}
        assert not any(caps[key] for key in ('supportsUnknownAccessibilityInclusion','supportsWeather','supportsCourseAdjustment'))
        sid = session['sessionId']
        profile = ready(mobility)
        profile['companions'] = {'value': {'type':'FAMILY','count':3,'hasInfant':False},'source':'USER','strength':'SOFT'}
        saved = client.put(f'/api/sessions/{sid}/profile', json={'profile':profile,'expectedProfileRevision':0})
        assert saved.status_code == 200 and saved.json()['status'] == 'READY'
        score_profile = Profile.model_validate(saved.json()['profile'])
        assert service.scheduler.scorer(synthetic_place('score', category='EXHIBITION'), score_profile) == 3
        assert service.scheduler.scorer(synthetic_place('score', category='EXHIBITION'), Profile.model_validate(ready(mobility))) == 0
        response = client.post('/api/courses', json={'sessionId':sid,'profileRevision':saved.json()['profileRevision']})
        assert response.status_code == 200
        body = response.json()
        CONTRACT['check'](body, CONTRACT['schemas']['CourseResponse'])
        assert body['status'] == 'SUCCESS'
        assert ('INJURY_RULES' in {w['code'] for w in body['warnings']}) == (mobility == ['INJURY'])
        for item in body['course']['items']:
            detail = client.get('/api/places/'+item['place']['id'])
            assert detail.status_code == 200 and detail.json()['place'] == item['place']
        unsupported = deepcopy(saved.json()['profile'])
        unsupported['includeUnknownAccessibility'] = True
        assert client.put(f'/api/sessions/{sid}/profile',json={'profile':unsupported,'expectedProfileRevision':1}).status_code == 422
        assert client.delete(f'/api/sessions/{sid}').status_code == 204
    assert ordinary_app.state.course_service is None and ordinary_app.state.capabilities.supportedAreas == []
    assert hashlib.sha256(stored[0].read_bytes()).hexdigest() == before


@pytest.mark.parametrize('failure', ['no-env','missing-file','corrupt','missing-schema','unapproved-weights'])
def test_runtime_startup_rejects_missing_or_invalid_dependencies(stored, tmp_path, monkeypatch, failure):
    monkeypatch.setenv('BUSANFIT_DB_PATH', str(stored[0]))
    if failure == 'no-env':
        monkeypatch.delenv('BUSANFIT_DB_PATH')
    elif failure == 'missing-file':
        monkeypatch.setenv('BUSANFIT_DB_PATH', str(tmp_path/'missing.sqlite3'))
    elif failure in ('corrupt','missing-schema'):
        path = tmp_path/'bad.sqlite3'
        path.write_bytes(b'not a SQLite database' if failure == 'corrupt' else b'')
        monkeypatch.setenv('BUSANFIT_DB_PATH', str(path))
    else:
        from app.application import course_connection
        original = course_connection.load_companion_proposal
        draft = json.loads((Path(__file__).resolve().parents[2]/'config/companion-weights.proposal.json').read_text(encoding='utf-8'))
        draft.update(status='PROPOSAL',pmApproved=False)
        draft_path = tmp_path/'draft.json'
        draft_path.write_text(json.dumps(draft),encoding='utf-8')
        monkeypatch.setattr(course_connection,'load_companion_proposal',lambda *args,**kwargs:original(draft_path,**kwargs))
    app = create_runtime_app()
    with pytest.raises((ValueError, RuntimeError, RepositoryError)):
        with TestClient(app):
            pytest.fail('invalid startup must not serve requests')
    assert app.state.course_service is None and app.state.capabilities.supportedAreas == []
    assert not (tmp_path/'missing.sqlite3').exists()


def test_runtime_rejects_mixed_injected_dependencies():
    with pytest.raises(ValueError,match='injected'):
        create_app(connect_real_data=True,course_service=object())


def test_database_evaluator_can_audit_the_runtime_startup(stored, tmp_path, monkeypatch):
    from test_course_connection import dataset, runner
    from app.application.course_connection import prepare_runtime_connection
    monkeypatch.setenv('BUSANFIT_DB_PATH',str(stored[0]))
    monkeypatch.delenv('BUSANFIT_WALK_RADIUS_M',raising=False)
    result=runner.evaluate_database(prepare_runtime_connection(),dataset(tmp_path),synthetic=True,runtime_app=create_runtime_app())
    assert result['appMode']=='runtime' and result['automatedChecksPassed']
    assert result['executedScenarios']==4 and result['excludedScenarios']==1
    assert result['hardViolations']==result['missingPlaceIds']==0
