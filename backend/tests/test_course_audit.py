"""Keep the independent response auditor and its negative controls in CI."""
from copy import deepcopy
from pathlib import Path
import runpy

import pytest
from test_courses import env, seed, generate, ready

audit = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'evaluation/courses/audit.py'))['audit_response']


@pytest.mark.parametrize('mobility', [None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']])
def test_independent_audit_of_http_response(env, mobility):
    profile = seed(env, ready(mobility))['profile']
    response = generate(env)
    assert response.status_code == 200
    result = audit(response.json(), profile, 1, env['repository'], env['travel'], {p.id: 100 for p in env['places']})
    assert result['hardViolations'] == 0 and result['missingPlaceIds'] == 0


@pytest.mark.parametrize('fault', ['missing-id', 'unknown-hard', 'source', 'travel', 'summary'])
def test_independent_auditor_rejects_false_success(env, fault):
    profile = seed(env, ready(['INJURY']))['profile']
    body = deepcopy(generate(env).json())
    if fault == 'missing-id':
        body['course']['items'][0]['place']['id'] = 'synthetic:missing'
    elif fault == 'unknown-hard':
        body['course']['validation']['unverifiedFields'].append('mobility.wheelchair')
    elif fault == 'source':
        body['course']['sources'] = []
    elif fault == 'travel':
        body['course']['legs'][0]['minutes'] = 11
    else:
        body['course']['summary']['totalMinutes'] += 1
    with pytest.raises(AssertionError):
        audit(body, profile, 1, env['repository'], env['travel'], {p.id: 100 for p in env['places']})


@pytest.mark.parametrize('fault', ['transport', 'budget', 'includeUnknownAccessibility'])
def test_auditor_rejects_success_for_an_unsupported_profile(env, fault):
    profile = seed(env, ready())['profile']
    body = generate(env).json()
    if fault == 'transport':
        profile['transport'] = {'value': 'CAR', 'source': 'USER', 'strength': 'HARD'}
    elif fault == 'budget':
        profile['budget'] = {'value': {'amount': 0, 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['FOOD']},
                             'source': 'USER', 'strength': 'HARD'}
    else:
        profile[fault] = True
    with pytest.raises(AssertionError):
        audit(body, profile, 1, env['repository'], env['travel'], {p.id: 100 for p in env['places']})
