"""Validated AI extraction followed by deterministic, conservative fallback."""
from datetime import timedelta, timezone
from dataclasses import dataclass, field
from typing import Literal, Protocol
from pydantic import Field, StrictBool, StrictInt, model_validator
from app.api.profile_models import Profile, ProfileField
from app.api.session_models import ContractModel


FIELD_MAP = {'area': 'area', 'time_window': 'timeWindow', 'transport': 'transport',
             'mobility': 'mobility', 'budget': 'budget', 'indoor_preference': 'indoorPreference',
             'companions': 'companions', 'excluded_categories': 'excludedCategories',
             'preference_tags': 'preferenceTags'}
SOFT = {'transport', 'indoorPreference', 'companions', 'preferenceTags'}


def blank_profile():
    return {**{name: {'value': None, 'source': 'UNSET',
                     'strength': 'SOFT' if name in SOFT else 'HARD'}
               for name in FIELD_MAP.values()}, 'includeUnknownAccessibility': False}


@dataclass(repr=False)
class Analysis:
    profile: dict
    unconfirmed_fields: set[str] = field(default_factory=set)
    companion_hints: dict = field(default_factory=dict)
    fallback: bool = False
    failure: str | None = None


class Extractor(Protocol):
    async def extract(self, message: str) -> Analysis: ...


class Hints(ContractModel):
    type: Literal['SOLO', 'FRIENDS', 'COUPLE', 'FAMILY', 'OTHER'] | None = None
    count: StrictInt | None = Field(default=None, ge=1)
    hasInfant: StrictBool | None = None
    hasChild: StrictBool | None = None


class ExtractionOutput(ContractModel):
    profile: Profile
    unconfirmedFields: list[ProfileField] = Field(default_factory=list)
    companionHints: Hints = Field(default_factory=Hints)

    @model_validator(mode='after')
    def extracted_values_are_explicit(self):
        # Defaults belong to deterministic policy, never to the provider.
        for name, condition in self.profile.model_dump(mode='json').items():
            if name == 'includeUnknownAccessibility':
                continue
            if (condition['value'] is None) != (condition['source'] == 'UNSET'):
                raise ValueError('null and UNSET must correspond')
            if condition['source'] == 'DEFAULT':
                raise ValueError('provider cannot assign defaults')
            if name in ('area', 'timeWindow', 'mobility', 'budget', 'excludedCategories') and condition['strength'] != 'HARD':
                raise ValueError('hard condition required')
            if isinstance(condition['value'], list) and len(condition['value']) != len(set(condition['value'])):
                raise ValueError('duplicate values')
        if self.profile.includeUnknownAccessibility:
            raise ValueError('unknown accessibility is outside extraction scope')
        if self.profile.companions.value is not None:
            companions = self.profile.companions.value.model_dump()
            for key, value in self.companionHints.model_dump(exclude_none=True).items():
                if key in companions and companions[key] != value:
                    raise ValueError('conflicting companion hints')
        window = self.profile.timeWindow.value
        if window is not None:
            seoul = timezone(timedelta(hours=9))
            if window.startAt >= window.endAt or window.startAt.astimezone(seoul).date() != window.endAt.astimezone(seoul).date():
                raise ValueError('invalid time window')
        return self


class AIConditionExtractor:
    def __init__(self, ai, parser):
        self.ai, self.parser = ai, parser

    async def extract(self, message: str) -> Analysis:
        from app.ai.service import Purpose
        result = await self.ai.complete(Purpose.EXTRACT, ExtractionOutput, user_message=message)
        if result.data is not None:
            profile = result.data.profile.model_dump(mode='json')
            if profile['transport']['value'] is None and 'transport' not in result.data.unconfirmedFields:
                profile['transport'] = {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'SOFT'}
            return Analysis(profile,
                            set(result.data.unconfirmedFields),
                            result.data.companionHints.model_dump(exclude_none=True))
        parsed = self.parser.parse(message)
        profile = blank_profile()
        hints = {}
        for name, condition in parsed.conditions.items():
            value = condition.value
            if name == 'time_window' and value is not None:
                value = {'startAt': value.start_at.isoformat(), 'endAt': value.end_at.isoformat()}
            elif name == 'companions' and value is not None:
                hints = {key: val for key, val in
                         [('type', value.type), ('count', value.count), ('hasInfant', value.has_infant),
                          ('hasChild', value.has_child)]
                         if val is not None}
                value = {key: hints[key] for key in ('type', 'count', 'hasInfant')} if all(
                    key in hints for key in ('type', 'count', 'hasInfant')) else None
            elif isinstance(value, tuple):
                value = list(value)
            profile[FIELD_MAP[name]] = {'value': value,
                                      'source': condition.source if value is not None else 'UNSET',
                                      'strength': condition.strength}
        return Analysis(profile, {FIELD_MAP[name] for name in parsed.unconfirmed_fields},
                        hints, True, result.failure)


def build_extractor():
    from app.ai.service import AIService
    from app.ai.gemini import configured_provider
    from app.constraints.chat_parser import ChatRuleParser
    return AIConditionExtractor(AIService(configured_provider()), ChatRuleParser())
