"""FR-015 contract. Runtime support follows successful dependency preparation."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictStr, model_validator
from app.api.course_models import Course, CourseResponseBase, PositiveInt
from app.api.profile_models import Category, ProfileField
from app.api.session_models import ContractModel

Operation = Literal['REMOVE', 'REPLACE', 'EXTEND_STAY', 'INDOOR', 'INCLUDE_UNKNOWN', 'UNCLEAR', 'PROFILE_CHANGE']


class AdjustmentRequest(ContractModel):
    sessionId: UUID
    expectedProfileRevision: PositiveInt
    message: Annotated[StrictStr, Field(min_length=1, max_length=1000)]


class ChangeIntent(ContractModel):
    op: Operation
    targets: Annotated[list[PositiveInt], Field(max_length=6)]
    category: Category | None = None
    minutes: Annotated[PositiveInt, Field(le=1440)] | None = None
    field: ProfileField | None = None

    @model_validator(mode='after')
    def consistent_operation(self):
        if len(self.targets) != len(set(self.targets)):
            raise ValueError('duplicate targets')
        if self.op != 'REPLACE' and self.category is not None:
            raise ValueError('category only belongs to replacement')
        if self.op != 'EXTEND_STAY' and self.minutes is not None:
            raise ValueError('minutes only belongs to extension')
        if self.op != 'PROFILE_CHANGE' and self.field is not None:
            raise ValueError('field only belongs to profile routing')
        return self


class AdjustmentIntent(ChangeIntent):
    followUp: Annotated[list[ChangeIntent], Field(max_length=4)] = Field(default_factory=list)


class AdjustmentQuestion(ContractModel):
    field: Annotated[StrictStr, Field(pattern=r'^(adjustment\.(target|minutes|message|followUp)|profile\.(area|timeWindow|transport|mobility|budget|indoorPreference|companions|excludedCategories|preferenceTags))$')]
    message: StrictStr


class ReplacedItem(ContractModel):
    oldItemId: StrictStr
    newItemId: StrictStr


class AdjustmentChanges(ContractModel):
    removedItemIds: list[StrictStr] = Field(default_factory=list)
    replacedItems: list[ReplacedItem] = Field(default_factory=list)
    timeChangedItemIds: list[StrictStr] = Field(default_factory=list)


class AdjustmentResponse(CourseResponseBase):
    status: Literal['SUCCESS', 'NEEDS_INPUT', 'NOT_APPLIED']
    profileRevision: PositiveInt
    course: Course
    changes: AdjustmentChanges = Field(default_factory=AdjustmentChanges)
    questions: Annotated[list[AdjustmentQuestion], Field(max_length=2)] = Field(default_factory=list)

    @model_validator(mode='after')
    def status_matches_content(self):
        if self.status == 'NEEDS_INPUT' and not self.questions:
            raise ValueError('questions required')
        if self.status != 'SUCCESS' and any(self.changes.model_dump().values()):
            raise ValueError('unapplied response cannot report changes')
        if self.course.profileRevision != self.profileRevision:
            raise ValueError('course profile revision mismatch')
        return self
