"""The provider schema must enforce the same HARD rules as local validation."""
import asyncio
import json

import pytest
from pydantic import ValidationError

from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService, Purpose
from app.api.profile_models import Profile
from app.application.extraction import ExtractionOutput, blank_profile


HARD_VALUES = {
    'area': 'HAEUNDAE',
    'timeWindow': {'startAt': '2026-11-23T13:00:00+09:00',
                   'endAt': '2026-11-23T17:00:00+09:00'},
    'mobility': ['WHEELCHAIR'],
    'budget': {'amount': 10000, 'currency': 'KRW', 'basis': 'TOTAL',
               'includes': ['ADMISSION']},
    'excludedCategories': ['CAFE'],
}


def resolve(schema, node):
    return schema['$defs'][node['$ref'].split('/')[-1]]


@pytest.mark.parametrize('field', HARD_VALUES)
def test_provider_schema_forbids_soft_on_fixed_hard_fields(field):
    schema = ExtractionOutput.model_json_schema()
    profile = resolve(schema, schema['properties']['profile'])
    condition = resolve(schema, profile['properties'][field])
    assert condition['properties']['strength']['const'] == 'HARD'
    assert 'strength' in condition['required']


@pytest.mark.parametrize('field', HARD_VALUES)
@pytest.mark.parametrize('is_unset', [False, True])
def test_wrong_hard_strength_identifies_the_field_without_normalizing(field, is_unset):
    profile = blank_profile()
    profile[field] = {'value': None if is_unset else HARD_VALUES[field],
                      'source': 'UNSET' if is_unset else 'USER', 'strength': 'SOFT'}
    with pytest.raises(ValidationError) as error:
        ExtractionOutput.model_validate({'profile': profile})
    assert ('profile', field, 'strength') in {e['loc'] for e in error.value.errors()}
    assert profile[field]['strength'] == 'SOFT'


def test_invalid_strength_is_retried_and_corrected_without_changing_values():
    valid = blank_profile()
    valid['mobility'] = {'value': ['WHEELCHAIR'], 'source': 'USER', 'strength': 'HARD'}
    invalid = json.loads(json.dumps(valid))
    invalid['mobility']['strength'] = 'SOFT'

    class Inspect(FakeProvider):
        async def complete(self, request):
            if self.calls == 1:
                assert '확인할 필드: profile' in request.system_prompt
            return await super().complete(request)

    provider = Inspect([FakeReply(json.dumps({'profile': invalid})),
                        FakeReply(json.dumps({'profile': valid}))])
    result = asyncio.run(AIService(provider).complete(
        Purpose.EXTRACT, ExtractionOutput, user_message='synthetic'))
    assert result.attempts == 2 and result.failure is None
    assert result.data.profile.model_dump(mode='json') == valid


def test_public_profile_still_allows_soft_fields_and_hard_promotions():
    schema = Profile.model_json_schema()
    condition = resolve(schema, schema['properties']['transport'])
    assert set(condition['properties']['strength']['enum']) == {'HARD', 'SOFT'}
    profile = blank_profile()
    profile['transport'] = {'value': 'WALK', 'source': 'USER', 'strength': 'HARD'}
    assert ExtractionOutput.model_validate({'profile': profile}).profile.transport.strength == 'HARD'
