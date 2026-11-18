"""Course -> edit field -> save USER -> regenerate via real HTTP handlers."""
from copy import deepcopy
import pytest
from app.ai.service import AIService
from app.application.extraction import blank_profile
from app.explanations.fakes import SyntheticExplanationProvider
from app.explanations.generator import ExplanationGenerator
from app.ai.gemini import UnconfiguredProvider
from test_courses import env, seed, generate, ready, check_contract


def fields(body):
    return [suggestion['field'] for suggestion in body['suggestions']]


def infant_profile():
    profile = ready()
    profile['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': True},
                             'source': 'USER', 'strength': 'SOFT'}
    return profile


def save(env, profile, revision=1):
    return env['client'].put('/api/sessions/' + env['sid'] + '/profile',
        json={'profile': profile, 'expectedProfileRevision': revision})


def test_success_includes_only_actual_profile_defaults_without_changing_profile(env):
    saved = seed(env)
    before = env['store'].check_current(env['sid'], 1)
    response = generate(env)
    check_contract(response)
    body = response.json()
    assert fields(body) == ['transport']
    assert body['suggestions'][0]['type'] == 'EDIT_PROFILE'
    assert body['suggestions'][0]['id'] == 'edit-default-transport'
    assert body['course']['profileRevision'] == 1
    after = env['store'].check_current(env['sid'], 1)
    assert after.profile == saved['profile'] == before.profile
    assert after.history == before.history and after.pending_fields == before.pending_fields


@pytest.mark.parametrize('mobility', [None, ['WHEELCHAIR'], ['STROLLER'], ['INJURY']])
def test_explicit_choices_generate_no_default_suggestions(env, mobility):
    profile = ready(mobility)
    profile['transport'] = {'value': 'WALK', 'source': 'USER', 'strength': 'SOFT'}
    seed(env, profile)
    body = generate(env).json()
    assert body['status'] == 'SUCCESS' and body['suggestions'] == []


def test_infant_auto_stroller_remains_hard_and_only_prompts_to_edit(env):
    saved = seed(env, infant_profile())
    body = generate(env).json()
    assert fields(body) == ['transport', 'mobility']
    assert saved['profile']['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
    assert all(i['place']['accessibility']['stroller'] is True for i in body['course']['items'])
    assert env['store'].check_current(env['sid'], 1).profile['mobility'] == saved['profile']['mobility']


def test_user_confirmation_removes_suggestions_after_save_and_new_revision(env):
    saved = seed(env, infant_profile())
    first = generate(env).json()
    assert fields(first) == ['transport', 'mobility']
    edited = deepcopy(saved['profile'])
    for suggestion in first['suggestions']:
        edited[suggestion['field']]['source'] = 'USER'  # Same values explicitly confirmed on the card.
    response = save(env, edited)
    assert response.status_code == 200 and response.json()['profileRevision'] == 2
    assert generate(env, 1).status_code == 409
    regenerated = generate(env, 2)
    check_contract(regenerated)
    assert regenerated.json()['suggestions'] == []
    assert regenerated.json()['course']['profileRevision'] == 2


def test_user_stroller_removal_is_never_automatically_reapplied(env):
    saved = seed(env, infant_profile())
    assert 'mobility' in fields(generate(env).json())
    edited = deepcopy(saved['profile'])
    edited['mobility'] = {'value': [], 'source': 'USER', 'strength': 'HARD'}
    result = save(env, edited)
    assert result.status_code == 200
    assert result.json()['profile']['mobility'] == edited['mobility']
    for _ in range(2):
        body = generate(env, 2).json()
        assert body['status'] == 'SUCCESS' and fields(body) == ['transport']
    assert env['store'].check_current(env['sid'], 2).profile['mobility'] == edited['mobility']


def test_unmodified_default_echo_and_repeated_generation_keep_stable_edit_links(env):
    saved = seed(env)
    first = generate(env).json()['suggestions']
    assert first == generate(env).json()['suggestions']
    response = save(env, saved['profile'])
    assert response.status_code == 200
    assert generate(env, 2).json()['suggestions'] == first


def test_unsupported_manual_change_is_422_and_keeps_default_suggestion(env):
    saved = seed(env)
    edited = deepcopy(saved['profile'])
    edited['transport'] = {'value': 'CAR', 'source': 'USER', 'strength': 'SOFT'}
    response = save(env, edited)
    assert response.status_code == 422
    assert env['store'].check_current(env['sid'], 1).profile == saved['profile']
    assert fields(generate(env).json()) == ['transport']


@pytest.mark.parametrize('legacy', ['transport', 'mobility'])
def test_generation_uses_normalized_defaults_even_when_not_in_saved_profile(env, legacy):
    profile = ready() if legacy == 'transport' else infant_profile()
    env['store'].commit_profile(env['sid'], 0, profile=profile, history=[])
    response = generate(env)
    check_contract(response)
    body = response.json()
    assert fields(body) == (['transport'] if legacy == 'transport' else ['transport', 'mobility'])
    # Course read does not silently persist defaults or increment revision.
    assert env['store'].check_current(env['sid'], 1).profile == profile


def test_legacy_infant_default_is_filtered_out_when_mobility_is_not_editable(env):
    profile = infant_profile()
    env['store'].commit_profile(env['sid'], 0, profile=profile, history=[])
    env['app'].state.capabilities.supportedProfileFields.remove('mobility')
    response = generate(env)
    # A non-supported actual constraint is rejected before producing edit links.
    assert response.status_code == 422 and 'suggestions' not in response.json()


@pytest.mark.parametrize('provider', [SyntheticExplanationProvider, UnconfiguredProvider])
def test_suggestions_coexist_with_explanation_success_or_template_fallback(env, provider):
    seed(env, infant_profile())
    env['app'].state.explanation_generator = ExplanationGenerator(AIService(provider()), env['repository'])
    response = generate(env)
    check_contract(response)
    body = response.json()
    assert fields(body) == ['transport', 'mobility']
    method = 'LLM' if provider is SyntheticExplanationProvider else 'TEMPLATE'
    assert all(i['reasonMethod'] == method for i in body['course']['items'])


def test_insufficient_response_has_no_suggestions_even_with_defaults(env):
    seed(env, infant_profile())
    env['retriever'].places = env['retriever'].places[:1]
    response = generate(env)
    check_contract(response)
    assert response.json()['status'] == 'INSUFFICIENT_PLACES'
    assert response.json()['suggestions'] == []


def test_incomplete_profile_has_no_suggestions_and_never_calls_retrieval(env):
    env['store'].commit_profile(env['sid'], 0, profile=blank_profile(), history=[])
    response = generate(env)
    assert response.status_code == 422 and 'suggestions' not in response.json()
    assert env['retriever'].calls == 0
