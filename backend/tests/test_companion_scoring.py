"""Pure draft scores, settings validation and ordinary-path isolation."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import pytest
from app.api.profile_models import Profile
from app.application.extraction import blank_profile
from app.courses.companion_scoring import CompanionProposal, ProposalCompanionScorer, load_companion_proposal
from app.courses.fakes import synthetic_place, synthetic_service
from app.courses.scheduler import default_score
from app.main import create_app

PROPOSAL_PATH = Path(__file__).resolve().parents[2] / 'config/companion-weights.proposal.json'


def profile(kind=None, *, count=3, infant=False, strength='SOFT'):
    values = blank_profile()
    if kind:
        values['companions'] = {'value': {'type': kind, 'count': count, 'hasInfant': infant},
                                'source': 'USER', 'strength': strength}
    return Profile.model_validate(values)


@pytest.mark.parametrize('kind,category,expected', [('COUPLE', 'CAFE', 3), ('FAMILY', 'EXHIBITION', 3),
    ('FAMILY', 'ATTRACTION', 3), ('FAMILY', 'PARK', 3), ('FRIENDS', 'ATTRACTION', 3),
    ('FRIENDS', 'PARK', 2), ('SOLO', 'CAFE', 0), ('OTHER', 'EXHIBITION', 0), (None, 'CAFE', 0)])
def test_explicit_draft_table_scores(kind, category, expected):
    assert ProposalCompanionScorer(load_companion_proposal())(synthetic_place('x', category=category), profile(kind)) == expected


def test_soft_indoor_and_companion_weights_are_composed_with_breakdown():
    scorer = ProposalCompanionScorer(load_companion_proposal())
    value = profile('COUPLE')
    value.indoorPreference.value, value.indoorPreference.source = 'INDOOR', 'USER'
    parts = scorer.breakdown(synthetic_place('x', category='CAFE'), value)
    assert (parts.indoor, parts.companion_category, parts.total) == (2, 3, 5)
    assert scorer(synthetic_place('x', category='CAFE', indoor=False), value) == 3
    value.indoorPreference.strength = 'HARD'
    assert scorer.breakdown(synthetic_place('x'), value).indoor == 0


def test_no_inference_from_text_price_count_or_infant_information():
    scorer = ProposalCompanionScorer(load_companion_proposal())
    first = synthetic_place('x', category='OTHER')
    altered = replace(first, name='[가상] 분위기 야경 체험 가성비', overview='[가상] 단체 적합 무료 야경',
                      price_amount=0, price_text='[가상] 무료', indoor=None)
    assert scorer(first, profile('FRIENDS', count=2)) == scorer(altered, profile('FRIENDS', count=100, infant=True)) == 0


def test_hard_companion_does_not_become_a_soft_score():
    assert ProposalCompanionScorer(load_companion_proposal())(synthetic_place('x'), profile('COUPLE', strength='HARD')) == 0


def test_settings_are_deeply_immutable_and_detached_from_caller():
    data = json.loads(PROPOSAL_PATH.read_text(encoding='utf-8'))
    proposal = CompanionProposal('test', 2, 1, data['categoryWeights'])
    data['categoryWeights']['COUPLE']['CAFE'] = 99
    assert proposal.category_weights['COUPLE']['CAFE'] == 3
    with pytest.raises(TypeError): proposal.category_weights['COUPLE']['CAFE'] = 9
    with pytest.raises(FrozenInstanceError): proposal.indoor_weight = 9


@pytest.mark.parametrize('bad', [True, False, -1, float('nan'), float('inf'), -float('inf'), '2', None, 10**400])
@pytest.mark.parametrize('target', ['indoor', 'companion', 'category'])
def test_invalid_numbers_are_rejected(bad, target):
    original = load_companion_proposal()
    values = {kind: dict(weights) for kind, weights in original.category_weights.items()}
    if target == 'category': values['COUPLE']['CAFE'] = bad
    with pytest.raises(ValueError):
        CompanionProposal('test', bad if target == 'indoor' else 2, bad if target == 'companion' else 1, values)


@pytest.mark.parametrize('mutation', ['missing-kind', 'extra-kind', 'missing-category', 'extra-category'])
def test_incomplete_or_unknown_mapping_is_not_silently_filled(mutation):
    values = json.loads(PROPOSAL_PATH.read_text(encoding='utf-8'))['categoryWeights']
    if mutation == 'missing-kind': del values['SOLO']
    if mutation == 'extra-kind': values['UNKNOWN'] = values['SOLO']
    if mutation == 'missing-category': del values['COUPLE']['CAFE']
    if mutation == 'extra-category': values['COUPLE']['NIGHT_VIEW'] = 3
    with pytest.raises(ValueError): CompanionProposal('test', 2, 1, values)


@pytest.mark.parametrize('mutation', ['approved', 'status', 'missing-key', 'extra-key'])
def test_loader_rejects_approval_relabeling_and_invalid_shape(tmp_path, mutation):
    data = json.loads(PROPOSAL_PATH.read_text(encoding='utf-8'))
    if mutation == 'approved': data['pmApproved'] = True
    if mutation == 'status': data['status'] = 'APPROVED'
    if mutation == 'missing-key': del data['categoryWeights']
    if mutation == 'extra-key': data['activate'] = True
    path = tmp_path / 'proposal.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError): load_companion_proposal(path)


@pytest.mark.parametrize('text', ['{"version":"a","version":"b"}', '{"version":NaN}', '[]', 'null'])
def test_loader_rejects_duplicate_keys_nonfinite_constants_and_nonobjects(tmp_path, text):
    path = tmp_path / 'proposal.json'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError): load_companion_proposal(path)


def test_overflow_is_an_error_not_a_neutral_score():
    original = load_companion_proposal()
    values = {kind: dict(weights) for kind, weights in original.category_weights.items()}
    values['COUPLE']['CAFE'] = 1e308
    scorer = ProposalCompanionScorer(CompanionProposal('overflow', 2, 1e308, values))
    with pytest.raises(ValueError): scorer(synthetic_place('x'), profile('COUPLE'))


def test_score_is_deterministic_without_mutating_records_or_profile():
    place, value = synthetic_place('x'), profile('COUPLE')
    before, place_before = value.model_dump(), deepcopy(place)
    scorer = ProposalCompanionScorer(load_companion_proposal())
    assert scorer(place, value) == scorer(place, value)
    assert value.model_dump() == before and place == place_before


def test_ordinary_app_and_existing_course_service_never_load_proposal(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('proposal must not load')
    monkeypatch.setattr('app.courses.companion_scoring.load_companion_proposal', forbidden)
    app = create_app()
    assert not app.state.capabilities.supportedAreas
    service = synthetic_service()
    assert service.scheduler.scorer is default_score
    for kind in ('COUPLE', 'FAMILY', 'FRIENDS', 'SOLO', 'OTHER'):
        assert service.scheduler.scorer(synthetic_place('x'), profile(kind)) == 0
