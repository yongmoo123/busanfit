from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SessionRequest(ContractModel):
    pass


class Capabilities(ContractModel):
    supportedAreas: list[Literal['HAEUNDAE', 'SEOMYEON', 'GWANGALLI', 'NAMPO']]
    supportedTransports: list[Literal['WALK', 'PUBLIC', 'CAR']]
    supportedProfileFields: list[Literal['area', 'timeWindow', 'transport', 'mobility', 'budget', 'indoorPreference', 'companions', 'excludedCategories', 'preferenceTags']]
    supportsUnknownAccessibilityInclusion: bool
    supportsCourseAdjustment: bool
    supportsWeather: bool


class SessionResponse(ContractModel):
    sessionId: UUID
    expiresAt: datetime
    capabilities: Capabilities
    requestId: UUID
