"""Existing CourseRequest/CourseResponse wire contract. No new response states."""
from datetime import date, datetime
from typing import Annotated, Literal, get_args
from copy import deepcopy
from uuid import UUID
from urllib.parse import urlparse

from pydantic import AwareDatetime, Field, StrictBool, StrictFloat, StrictStr, field_validator, model_validator
from app.api.profile_models import Area, Category, NonnegativeInt, ProfileField, Timestamp, TimeWindow, Warning
from app.api.session_models import ContractModel

PositiveInt = Annotated[NonnegativeInt, Field(ge=1)]


class CourseRequest(ContractModel):
    sessionId: UUID
    profileRevision: PositiveInt


class Price(ContractModel):
    status: Literal['KNOWN', 'UNKNOWN']
    amount: NonnegativeInt | None
    currency: Literal['KRW']
    basis: Literal['PER_PERSON', 'TOTAL', 'UNKNOWN']


class Coordinates(ContractModel):
    latitude: Annotated[StrictFloat, Field(ge=-90, le=90)]
    longitude: Annotated[StrictFloat, Field(ge=-180, le=180)]


class OpenHours(ContractModel):
    status: Literal['KNOWN', 'UNKNOWN']
    description: StrictStr | None


class Evidence(ContractModel):
    field: Literal['wheelchair', 'stroller', 'elevator', 'accessibleToilet']
    sourceId: StrictStr
    note: StrictStr


class Accessibility(ContractModel):
    grade: Literal['VERIFIED', 'UNKNOWN', 'UNSUITABLE']
    wheelchair: StrictBool | None
    stroller: StrictBool | None
    elevator: StrictBool | None
    accessibleToilet: StrictBool | None
    evidence: list[Evidence]


class Place(ContractModel):
    id: StrictStr
    name: StrictStr
    category: Category
    area: Area
    address: StrictStr
    coordinates: Coordinates
    indoor: StrictBool | None
    openHours: OpenHours
    price: Price
    defaultStayMinutes: PositiveInt
    accessibility: Accessibility
    sourceIds: Annotated[list[StrictStr], Field(min_length=1)]


class Source(ContractModel):
    id: StrictStr
    provider: StrictStr
    datasetName: StrictStr
    url: StrictStr
    license: StrictStr | None
    baseDate: date | None
    retrievedAt: Timestamp

    @field_validator('url')
    @classmethod
    def valid_uri(cls, value):
        parts = urlparse(value)
        if not parts.scheme or not parts.netloc:
            raise ValueError('source URI required')
        return value


class CourseItem(ContractModel):
    id: StrictStr
    order: PositiveInt
    place: Place
    startAt: Timestamp
    endAt: Timestamp
    stayMinutes: PositiveInt
    reason: StrictStr
    reasonMethod: Literal['LLM', 'TEMPLATE']
    isAnchor: StrictBool


class Leg(ContractModel):
    fromItemId: StrictStr
    toItemId: StrictStr
    mode: Literal['WALK', 'PUBLIC', 'CAR']
    minutes: NonnegativeInt
    method: Literal['DISTANCE_ESTIMATE', 'STATION_DATA', 'ROUTING_API']
    isEstimate: StrictBool


class Summary(ContractModel):
    totalStayMinutes: NonnegativeInt
    totalTravelMinutes: NonnegativeInt
    totalWaitingMinutes: NonnegativeInt
    totalMinutes: NonnegativeInt
    estimatedCost: Price


class Validation(ContractModel):
    status: Literal['PASSED', 'CONDITIONAL']
    checkedHardConstraints: list[StrictStr]
    unverifiedFields: list[StrictStr]
    routeAccessibility: Literal['UNVERIFIED', 'VERIFIED']


class Course(ContractModel):
    id: UUID
    profileRevision: PositiveInt
    createdAt: AwareDatetime
    availableWindow: TimeWindow
    startAt: Timestamp
    endAt: Timestamp
    items: Annotated[list[CourseItem], Field(min_length=2, max_length=6)]
    legs: list[Leg]
    summary: Summary
    validation: Validation
    sources: Annotated[list[Source], Field(min_length=1)]


def _suggestion_schema(schema):
    """Expose the same coupled action/field branches in generated OpenAPI."""
    branches = []
    for action, fields in [('EDIT_PROFILE', list(get_args(ProfileField))),
                           ('INCLUDE_UNKNOWN_ACCESSIBILITY', ['includeUnknownAccessibility'])]:
        branch = deepcopy(schema)
        branch.pop('title', None)
        branch['properties']['type'] = {'type': 'string', 'enum': [action]}
        branch['properties']['field'] = {'type': 'string', 'enum': fields}
        branches.append(branch)
    schema.clear()
    schema.update(title='Suggestion', oneOf=branches)


class Suggestion(ContractModel):
    model_config = {'extra': 'forbid', 'json_schema_extra': _suggestion_schema}
    id: StrictStr
    type: Literal['EDIT_PROFILE', 'INCLUDE_UNKNOWN_ACCESSIBILITY']
    label: StrictStr
    field: ProfileField | Literal['includeUnknownAccessibility']

    @model_validator(mode='after')
    def action_matches_field(self):
        if (self.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY') != (self.field == 'includeUnknownAccessibility'):
            raise ValueError('suggestion action and field must match')
        return self


class ExcludedUnknown(ContractModel):
    count: NonnegativeInt
    fields: list[StrictStr]


class CourseResponseBase(ContractModel):
    suggestions: Annotated[list[Suggestion], Field(max_length=3)]
    warnings: list[Warning]
    excludedUnknown: ExcludedUnknown
    sessionExpiresAt: datetime
    requestId: UUID


class CourseSuccess(CourseResponseBase):
    status: Literal['SUCCESS']
    course: Course


class CourseInsufficient(CourseResponseBase):
    status: Literal['INSUFFICIENT_PLACES']
    course: None


CourseResponse = Annotated[CourseSuccess | CourseInsufficient, Field(discriminator='status')]
