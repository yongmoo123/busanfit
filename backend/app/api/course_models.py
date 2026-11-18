"""Existing CourseRequest/CourseResponse wire contract. No new response states."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from urllib.parse import urlparse

from pydantic import AwareDatetime, Field, StrictBool, StrictFloat, StrictStr, field_validator
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


class Suggestion(ContractModel):
    id: StrictStr
    type: Literal['EDIT_PROFILE']
    label: StrictStr
    field: ProfileField


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
