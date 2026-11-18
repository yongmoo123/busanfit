"""The scorer must not turn alternative/null expectations into false positives."""
from pathlib import Path
import runpy

score = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'evaluation/extraction/run.py'))['matches']


def test_acceptable_full_conditions_require_value_and_source():
    expected = {'acceptable': [{'value': 'ANY', 'source': 'USER', 'strength': 'SOFT'},
                               {'value': None, 'source': 'UNSET'}]}
    assert score({'value': None, 'source': 'UNSET', 'strength': 'SOFT'}, expected)
    assert not score({'value': 'INDOOR', 'source': 'USER', 'strength': 'HARD'}, expected)
    assert not score({'value': 'ANY', 'source': 'DEFAULT', 'strength': 'SOFT'}, expected)


def test_keywords_require_an_explicit_user_value():
    expected = {'keywordsAny': ['카페', '커피'], 'source': 'USER'}
    assert score({'value': ['커피'], 'source': 'USER', 'strength': 'SOFT'}, expected)
    assert not score({'value': ['커피'], 'source': 'DEFAULT', 'strength': 'SOFT'}, expected)
    assert not score({'value': None, 'source': 'UNSET', 'strength': 'SOFT'}, expected)
