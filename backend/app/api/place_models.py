"""Existing PlaceResponse contract; explanations belong to CourseItem."""
from typing import Annotated
from uuid import UUID
from pydantic import Field
from app.api.course_models import Place, Source
from app.api.profile_models import Warning
from app.api.session_models import ContractModel


class PlaceResponse(ContractModel):
    place: Place
    sources: Annotated[list[Source], Field(min_length=1)]
    warnings: list[Warning]
    requestId: UUID
