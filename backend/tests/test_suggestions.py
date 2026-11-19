"""FR-014 default edit links: eligibility, cap, determinism and no side effects."""
import pytest
from app.api.profile_models import Profile
from app.api.session_models import Capabilities
from app.application.extraction import blank_profile
from app.application.suggestions import build_default_suggestions


VALUES = {
    'area': 'HAEUNDAE',
    'transport': 'WALK',
    'timeWindow': {'startAt': '2026-11-17T13:00:00+09:00', 'endAt': '2026-11-17T18:00:00+09:00'},
    'mobility': ['STROLLER'],
    'budget': {'amount': 30000, 'currency': 'KRW', 'basis': 'TOTAL', 'includes': ['FOOD']},
    'companions': {'type': 'FAMILY', 'count': 3, 'hasInfant': True},
    'indoorPreference': 'INDOOR',
    'excludedCategories': ['CAFE'],
    'preferenceTags': ['가상 선호'],
}


def caps(fields=tuple(VALUES), *, areas=('HAEUNDAE',), transports=('WALK',)):
    return Capabilities(supportedAreas=list(areas), supportedTransports=list(transports),
        supportedProfileFields=list(fields), supportsUnknownAccessibilityInclusion=False,
        supportsCourseAdjustment=False, supportsWeather=False)


def profile(*names, source='DEFAULT'):
    values = blank_profile()
    for name in names:
        values[name] = {'value': VALUES[name], 'source': source, 'strength': values[name]['strength']}
    return Profile.model_validate(values)


@pytest.mark.parametrize('name', list(VALUES))
def test_each_existing_card_field_requires_an_applied_default(name):
    result = build_default_suggestions(profile(name), caps())
    assert len(result) == 1
    assert result[0].field == name and result[0].type == 'EDIT_PROFILE'
    assert result[0].id == f'edit-default-{name}' and result[0].label
    assert '해제' not in result[0].label


@pytest.mark.parametrize('source', ['USER', 'UNSET'])
def test_user_and_unset_fields_do_not_generate_suggestions(source):
    value = profile(*VALUES, source='USER') if source == 'USER' else Profile.model_validate(blank_profile())
    assert build_default_suggestions(value, caps()) == []


@pytest.mark.parametrize('name', list(VALUES))
def test_unsupported_fields_are_excluded(name):
    assert build_default_suggestions(profile(name), caps(fields=())) == []


@pytest.mark.parametrize('name', ['area', 'transport'])
def test_unsupported_enum_values_are_excluded_even_if_field_is_enabled(name):
    support = caps(areas=() if name == 'area' else ('HAEUNDAE',),
                   transports=() if name == 'transport' else ('WALK',))
    assert build_default_suggestions(profile(name), support) == []


def test_maximum_three_unique_fields_in_existing_card_order():
    # This is a synthetic future-default fixture, not an assertion that all
    # these fields are enabled/defaulted by the current production server.
    result = build_default_suggestions(profile(*reversed(VALUES)), caps())
    assert [s.field for s in result] == ['area', 'transport', 'timeWindow']
    assert len({s.id for s in result}) == len({s.field for s in result}) == 3


def test_unsupported_candidates_do_not_consume_limit():
    result = build_default_suggestions(profile(*VALUES), caps(fields=('mobility', 'companions', 'excludedCategories', 'preferenceTags')))
    assert [s.field for s in result] == ['mobility', 'companions', 'excludedCategories']


def test_result_is_deterministic_and_does_not_mutate_or_alias_inputs():
    value, support = profile('transport', 'mobility'), caps()
    before, caps_before = value.model_dump(), support.model_dump()
    first = build_default_suggestions(value, support)
    assert first == build_default_suggestions(value, support)
    first[0].label = 'changed'
    assert build_default_suggestions(value, support)[0].label != 'changed'
    assert value.model_dump() == before and support.model_dump() == caps_before


def test_no_raw_values_or_stay_weather_unknown_actions_in_output():
    value = profile('transport', 'mobility', 'preferenceTags')
    result = [s.model_dump() for s in build_default_suggestions(value, caps())]
    assert all(set(s) == {'id', 'type', 'label', 'field'} for s in result)
    assert '가상 선호' not in str(result) and 'STROLLER' not in str(result)
    assert all(s['field'] in VALUES for s in result)
    assert 'stay' not in str(result).lower() and 'weather' not in str(result).lower()


def test_explicit_empty_default_list_differs_from_unknown():
    value = profile('excludedCategories')
    value.excludedCategories.value = []
    assert [s.field for s in build_default_suggestions(value, caps())] == ['excludedCategories']
    assert build_default_suggestions(Profile.model_validate(blank_profile()), caps()) == []
