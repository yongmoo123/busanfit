"""The modification scorer must not pass wrong targets, params or a dropped follow-up."""
import asyncio
from pathlib import Path
import json
import runpy

RUN = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'evaluation/adjust/run.py'))
matches = RUN['matches']


def intent(op, targets, **extra):
    return {'op': op, 'targets': targets, 'category': None, 'minutes': None, 'field': None,
            'followUp': [], **extra}


def test_targets_and_named_params_are_scored():
    expected = {'op': 'REPLACE', 'targets': [1], 'params': {'category': 'CAFE'}}
    assert matches(intent('REPLACE', [1], category='CAFE'), expected)
    assert not matches(intent('REPLACE', [1]), expected)
    assert not matches(intent('REPLACE', [2], category='CAFE'), expected)


def test_null_params_mean_not_invented():
    expected = {'op': 'EXTEND_STAY', 'targets': [3], 'params': {'minutes': None}}
    assert matches(intent('EXTEND_STAY', [3]), expected)
    assert not matches(intent('EXTEND_STAY', [3], minutes=30), expected)


def test_acceptable_alternative_and_unscored_targets():
    expected = {'op': 'UNCLEAR', 'targets': None}
    acceptable = [{'op': 'REMOVE', 'targets': [5]}]
    assert matches(intent('UNCLEAR', []), expected, acceptable)
    assert matches(intent('REMOVE', [5]), expected, acceptable)
    assert not matches(intent('REMOVE', [5]), expected)
    assert not matches(intent('REMOVE', [4]), expected, acceptable)


def test_follow_up_must_be_kept():
    expected = {'op': 'REMOVE', 'targets': [2], 'followUp': {'op': 'INDOOR', 'targets': []}}
    assert matches(intent('REMOVE', [2], followUp=[intent('INDOOR', [])]), expected)
    assert not matches(intent('REMOVE', [2]), expected)


def test_profile_change_field():
    expected = {'op': 'PROFILE_CHANGE', 'field': 'timeWindow'}
    assert matches(intent('PROFILE_CHANGE', [], field='timeWindow'), expected)
    assert not matches(intent('EXTEND_STAY', [4], minutes=60), expected)


def test_rules_run_covers_every_case_without_model():
    dataset = json.loads((Path(__file__).resolve().parents[2] / 'evaluation/adjust/cases.json').read_text(encoding='utf-8'))
    interpreter = RUN['AdjustmentInterpreter'](None)
    report = asyncio.run(RUN['evaluate'](dataset, interpreter))
    assert len(report['cases']) == len(dataset['cases'])
    assert report['excluded'] == ['AD-16']
    by_id = {r['id']: r for r in report['cases']}
    assert by_id['AD-01']['verdict'] == 'PASS' and by_id['AD-01']['fallback']
    assert by_id['AD-18']['verdict'] == 'PASS'  # rule fallback gives UNCLEAR for a missing order
