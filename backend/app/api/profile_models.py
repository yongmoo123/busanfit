"""Typed profile contract; wire names follow the existing camelCase API."""
from datetime import datetime
import re
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, Field, StrictBool, StrictInt, StrictStr
from app.api.session_models import ContractModel


def rfc3339_string(value):
    if not isinstance(value, str) or not re.fullmatch(
        r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value
    ):
        raise ValueError('offset datetime string required')
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(rfc3339_string)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0)]
Area = Literal['HAEUNDAE', 'SEOMYEON', 'GWANGALLI', 'NAMPO']
Transport = Literal['WALK', 'PUBLIC', 'CAR']
ProfileField = Literal['area', 'timeWindow', 'transport', 'mobility', 'budget', 'indoorPreference', 'companions', 'excludedCategories', 'preferenceTags']
Category = Literal['CAFE', 'FOOD', 'EXHIBITION', 'ATTRACTION', 'PARK', 'SHOPPING', 'OTHER']
T = TypeVar('T')


class Condition(ContractModel, Generic[T]):
    value: T | None
    source: Literal['USER', 'DEFAULT', 'UNSET']
    strength: Literal['HARD', 'SOFT']


class TimeWindow(ContractModel):
    startAt: Timestamp
    endAt: Timestamp


class Budget(ContractModel):
    amount: NonnegativeInt
    currency: Literal['KRW']
    basis: Literal['PER_PERSON', 'TOTAL']
    includes: Annotated[list[Literal['ADMISSION', 'FOOD', 'TRANSPORT']], Field(min_length=1)]


class Companions(ContractModel):
    type: Literal['SOLO', 'FRIENDS', 'COUPLE', 'FAMILY', 'OTHER']
    count: Annotated[StrictInt, Field(ge=1)]
    hasInfant: StrictBool


class Profile(ContractModel):
    area: Condition[Area]
    timeWindow: Condition[TimeWindow]
    transport: Condition[Transport]
    mobility: Condition[list[Literal['WHEELCHAIR', 'STROLLER', 'INJURY']]]
    budget: Condition[Budget]
    indoorPreference: Condition[Literal['INDOOR', 'OUTDOOR', 'ANY']]
    companions: Condition[Companions]
    excludedCategories: Condition[list[Category]]
    preferenceTags: Condition[list[StrictStr]]
    includeUnknownAccessibility: StrictBool


class ProfileUpdateRequest(ContractModel):
    expectedProfileRevision: NonnegativeInt
    profile: Profile

    model_config = {
        'extra': 'forbid',
        'json_schema_extra': {'examples': [{
            'expectedProfileRevision': 0,
            'profile': {
                **{name: {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
                   for name in Profile.model_fields if name != 'includeUnknownAccessibility'},
                'includeUnknownAccessibility': False,
            },
        }]},
    }


class Question(ContractModel):
    field: ProfileField
    message: str


class Warning(ContractModel):
    code: str
    message: str
    placeIds: list[str]


class ProfileResponse(ContractModel):
    status: Literal['NEEDS_INPUT', 'READY']
    profile: Profile
    profileRevision: Annotated[int, Field(ge=1)]
    questions: Annotated[list[Question], Field(max_length=2)]
    warnings: list[Warning]
    sessionExpiresAt: datetime
    requestId: UUID
