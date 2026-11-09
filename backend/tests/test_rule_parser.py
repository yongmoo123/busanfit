"""Small grammar regression cases, not an LLM accuracy evaluation set."""
import pytest
from app.constraints.parser import RuleBasedParser


def parse(text):
    return RuleBasedParser().parse(text)


def test_explicit_area_time_and_transport():
    result = parse('2026-11-12 해운대에서, 오후 1시부터 오후 5시까지, 걸어서 이동')
    assert result.conditions['area'].value == 'HAEUNDAE'
    window = result.conditions['time_window'].value
    assert window.start_at.isoformat() == '2026-11-12T13:00:00+09:00'
    assert window.end_at.hour == 17
    assert result.conditions['transport'].value == 'WALK'
    assert result.conditions['transport'].source == 'USER'


@pytest.mark.parametrize('text', [
    '2026년 11월 12일 13시부터 17시까지',
    '2026-11-12 13:00부터 17:30까지',
    '2026-11-12 오전 9시부터 오후 1시까지',
])
def test_supported_time_formats(text):
    assert parse(text).conditions['time_window'].value is not None


@pytest.mark.parametrize('text', [
    '2026-11-12 113시부터 17시까지',
    '2026-11-123 13시부터 17시까지',
    '12026-11-12 13시부터 17시까지',
    '2026년 11월 123일 13시부터 17시까지',
    '2026-11-12 13시까지 17시부터',
    '2026-11-12 13시 130분부터 17시까지',
    '2026-11-12 13:000부터 17:00까지',
    '2026-11-12 13:00:30부터 17:00까지',
    '2026-11-12 13시부터 117시까지',
    '2026-11-12 13시부터 17:000까지',
    '2026-11-12 13시와 17시, 19시부터 20시까지',
    '2026-11-12 13시부터 14시까지, 16시부터 17시까지',
    '2026-11-12.5 13시부터 17시까지',
])
def test_malformed_tokens_are_not_accepted_as_valid_substrings(text):
    result = parse(text)
    assert result.conditions['time_window'].value is None
    assert result.conditions['time_window'].source == 'UNSET'
    assert 'time_window' in result.unconfirmed_fields


@pytest.mark.parametrize('text,start,end', [
    ('2026/11/12 13:05부터 17:30까지', (13, 5), (17, 30)),
    ('2026년 11월 12일 13시 5분부터 17시 30분까지', (13, 5), (17, 30)),
    ('2026-11-12 오전 12시부터 오후 12시까지', (0, 0), (12, 0)),
])
def test_valid_full_tokens_preserve_exact_minutes(text, start, end):
    window = parse(text).conditions['time_window'].value
    assert (window.start_at.hour, window.start_at.minute) == start
    assert (window.end_at.hour, window.end_at.minute) == end


@pytest.mark.parametrize('text', [
    '내일 오후에', '2026-11-12 1시부터 5시까지',
    '2026-11-12 17시부터 13시까지', '2026-11-12 13시부터 13시까지',
    '2026-02-30 13시부터 17시까지', '2026-11-12 23시부터 2026-11-13 오전 1시까지',
    '2026-11-12 13시부터 25시까지', '2026-11-12 13:99부터 17:00까지',
])
def test_ambiguous_invalid_time_stays_unset(text):
    result = parse(text)
    assert result.conditions['time_window'].value is None
    assert 'time_window' in result.unconfirmed_fields


@pytest.mark.parametrize('text', ['해운대 말고 남포', '해운대는 안가요', '서면이나 해운대', '서울에서 놀래요'])
def test_ambiguous_or_unhandled_area_is_not_defaulted(text):
    result = parse(text)
    assert result.conditions['area'].value is None
    assert 'area' in result.unconfirmed_fields


@pytest.mark.parametrize('text,value', [('도보','WALK'),('대중교통','PUBLIC'),('자차','CAR')])
def test_extracting_transport_does_not_claim_it_is_supported(text, value):
    assert parse(text).conditions['transport'].value == value


def test_absent_transport_uses_dec001_default_but_ambiguity_does_not():
    default = parse('해운대')
    assert default.conditions['transport'].value == 'WALK'
    assert default.conditions['transport'].source == 'DEFAULT'
    ambiguous = parse('자차 말고 도보')
    assert ambiguous.conditions['transport'].value is None
    assert 'transport' in ambiguous.unconfirmed_fields


def test_mobility_and_companion_hints_preserve_unknowns():
    result = parse('휠체어와 유모차 사용, 가족 3명과 아기 동반')
    assert result.conditions['mobility'].value == ('WHEELCHAIR','STROLLER')
    assert result.conditions['mobility'].strength == 'HARD'
    companions = result.conditions['companions'].value
    assert companions.type == 'FAMILY' and companions.count == 3 and companions.has_infant is True
    assert parse('친구와 함께').conditions['companions'].value.has_infant is None
    assert parse('친구와 함께').conditions['companions'].value.count is None


def test_infant_does_not_apply_pending_stroller_precedence():
    result = parse('아기 동반')
    assert result.conditions['companions'].value.has_infant is True
    assert result.conditions['mobility'].value is None


@pytest.mark.parametrize('text', ['휠체어는 안 써요', '유모차가 필요없어요', '휠체어가 아닌 유모차', '다리가 아파요', '계단은 못 올라가요'])
def test_negative_or_unsupported_mobility_grammar_requires_confirmation(text):
    result = parse(text)
    assert result.conditions['mobility'].value is None
    assert 'mobility' in result.unconfirmed_fields


def test_no_constraints_never_becomes_empty_mobility_or_free_budget():
    result = parse('해운대 공원')
    assert result.conditions['mobility'].value is None
    assert result.conditions['budget'].value is None
    assert 'budget' not in result.unconfirmed_fields
    assert parse('예산 2만원').conditions['budget'].source == 'UNSET'
    assert 'budget' in parse('예산 2만원').unconfirmed_fields


def test_indoor_preference_strength_and_negation():
    assert parse('실내 위주').conditions['indoor_preference'].strength == 'SOFT'
    assert parse('실내만 반드시').conditions['indoor_preference'].strength == 'HARD'
    result = parse('실내는 싫어요')
    assert result.conditions['indoor_preference'].value is None


@pytest.mark.parametrize('text,field', [('자차만 이용', 'transport'), ('꼭 걸어서 이동', 'transport'), ('실내에서만', 'indoor_preference')])
def test_explicit_hard_language_is_not_softened(text, field):
    assert parse(text).conditions[field].strength == 'HARD'


def test_exclusion_is_unconfirmed_instead_of_silently_discarded():
    result = parse('카페는 빼 주세요')
    assert result.conditions['excluded_categories'].value is None
    assert 'excluded_categories' in result.unconfirmed_fields
    assert not hasattr(result, 'status')


def test_results_are_isolated_and_diagnostics_do_not_echo_input():
    one = parse('부상 private-sentinel')
    two = parse('해운대')
    one.unconfirmed_fields.add('synthetic')
    assert 'synthetic' not in two.unconfirmed_fields
    assert 'private-sentinel' not in repr(one) + str(one.unconfirmed_fields) + str(one.warnings)


@pytest.mark.parametrize('text', ['', ' ', 'x'*1001, None])
def test_bad_input_is_rejected_without_echo(text):
    with pytest.raises(ValueError, match='message must'):
        parse(text)
