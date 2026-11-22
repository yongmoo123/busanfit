"""Synthetic DEC-020 state transitions; no real health data."""
from copy import deepcopy
import pytest
from app.constraints.mobility import normalize_mobility


def profile(infant=True, value=None, source='UNSET'):
    return {'companions': {'value': {'type': 'FAMILY', 'count': 2, 'hasInfant': infant},
                           'source': 'USER', 'strength': 'SOFT'},
            'mobility': {'value': value, 'source': source, 'strength': 'HARD'}}


def test_infant_applies_default_and_does_not_mutate_input():
    before = profile()
    original = deepcopy(before)
    result, warnings = normalize_mobility(before)
    assert result['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
    assert warnings == [] and before == original


@pytest.mark.parametrize('values', [[], ['INJURY'], ['WHEELCHAIR']])
def test_user_choice_and_removal_survive_repeated_infant_mentions(values):
    before = profile(value=values, source='USER')
    result, warnings = normalize_mobility(before)
    assert result == before
    assert [w['code'] for w in warnings] == ['STROLLER_NOT_APPLIED']
    repeated, _ = normalize_mobility(result)
    assert repeated == result


def test_user_stroller_is_kept_on_infant_cancellation():
    before = profile(False, ['INJURY', 'STROLLER'], 'USER')
    assert normalize_mobility(before) == (before, [])


@pytest.mark.parametrize('values,expected,source', [
    (['STROLLER'], None, 'UNSET'),
    (['STROLLER', 'WHEELCHAIR'], ['WHEELCHAIR'], 'DEFAULT'),
])
def test_cancellation_removes_only_automatic_stroller(values, expected, source):
    result, _ = normalize_mobility(profile(False, values, 'DEFAULT'))
    assert result['mobility']['value'] == expected
    assert result['mobility']['source'] == source


def test_null_reset_reapplies_default_and_unknown_is_not_false():
    removed, _ = normalize_mobility(profile(True, [], 'USER'))
    removed['mobility'] = {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
    reset, _ = normalize_mobility(removed)
    assert reset['mobility']['source'] == 'DEFAULT'
    reset['companions']['value'] = None
    assert normalize_mobility(reset)[0] == reset


def test_partial_infant_hint_can_normalize_without_inventing_companions():
    before = profile()
    before['companions']['value'] = None
    result, _ = normalize_mobility(before, has_infant=True)
    assert result['companions']['value'] is None
    assert result['mobility']['value'] == ['STROLLER']
