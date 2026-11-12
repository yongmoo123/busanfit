"""Partial extraction hints, not a complete/storable ConstraintProfile."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, repr=False)
class TimeRange:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, repr=False)
class CompanionHints:
    type: str | None = None
    count: int | None = None
    has_infant: bool | None = None


@dataclass(frozen=True, repr=False)
class ExtractedCondition:
    value: str | tuple[str, ...] | TimeRange | CompanionHints | None
    source: Literal['USER', 'DEFAULT', 'UNSET']
    strength: Literal['HARD', 'SOFT']


@dataclass(repr=False)
class Extraction:
    conditions: dict[str, ExtractedCondition] = field(default_factory=dict)
    # Field names only; never copy user text to diagnostics.
    unconfirmed_fields: set[str] = field(default_factory=set)
    warnings: tuple[str, ...] = ('RULE_PARSER_USED',)
