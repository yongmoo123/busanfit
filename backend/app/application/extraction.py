"""AI/fallback adapter. PR #17 supplies AIService and RuleBasedParser.

No provider is configured in production yet. Combined with #17, the unavailable
provider follows the same retry -> rule-parser path as a real provider failure.
"""
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
        return self


class AIConditionExtractor:
    def __init__(self, ai, parser):
        self.ai, self.parser = ai, parser

    async def extract(self, message: str) -> Analysis:
        from app.ai.service import Purpose
        result = await self.ai.complete(Purpose.EXTRACT, ExtractionOutput, user_message=message)
        if result.data is not None:
            return Analysis(result.data.profile.model_dump(mode='json'),
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
                         [('type', value.type), ('count', value.count), ('hasInfant', value.has_infant)]
                         if val is not None}
                value = hints if len(hints) == 3 else None
            elif isinstance(value, tuple):
                value = list(value)
            profile[FIELD_MAP[name]] = {'value': value,
                                      'source': condition.source if value is not None else 'UNSET',
                                      'strength': condition.strength}
        return Analysis(profile, {FIELD_MAP[name] for name in parsed.unconfirmed_fields},
                        hints, True, result.failure)


def build_extractor():
    """Keep #13 independently installable until its #17 dependency is merged."""
    try:
        from app.ai.service import AIService
        from app.constraints.parser import RuleBasedParser
    except ModuleNotFoundError as exc:
        if exc.name not in ('app.ai.service', 'app.constraints.parser'):
            raise
        return None

    class UnconfiguredProvider:
        async def complete(self, request):
            raise RuntimeError('provider is not configured')

    return AIConditionExtractor(AIService(UnconfiguredProvider()), RuleBasedParser())
