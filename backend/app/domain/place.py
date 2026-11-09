"""Place records shared by the course engine and PlaceRepository (FR-007, DEC-003, DEC-005).

Plain data only: no DB, HTTP or LLM imports. Field names mirror the columns of
``backend/app/data/schema.sql`` (SDD 5.2); API JSON (camelCase) is converted in ``app.api``.

Unknown stays unknown: ``None`` is never turned into "free", "accessible", "always open" or 0.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Contract (openapi Place.category) values. SDD 5.2 lists a different set
# (관광·문화·체험·야외·음식·카페); the mapping is pending PM decision (issue #7 "정할 것 2"),
# so the DB does not restrict the value and this tuple is informational.
CONTRACT_CATEGORIES = ("CAFE", "FOOD", "EXHIBITION", "ATTRACTION", "PARK", "SHOPPING", "OTHER")

ACCESSIBILITY_GRADES = ("VERIFIED", "UNKNOWN", "UNSUITABLE")


@dataclass(frozen=True)
class OpenHoursRecord:
    """Opening hours as stored.

    ``parsed``: normalized structure (``places.open_hours`` JSON) or ``None`` when absent or
    not parseable. Its shape is not fixed yet (issue #7 assumption 6).
    ``text``: original text from the source (``places.open_hours_text``) or ``None``.
    ``text`` present but ``parsed`` ``None`` means "known to the user, unverified for HARD checks".
    """
    parsed: Mapping[str, Any] | None
    text: str | None


@dataclass(frozen=True)
class AccessibilityRecord:
    """Barrier-free info for one place (``accessibility`` row). ``None`` items = no information."""
    grade: str
    wheelchair: bool | None
    stroller: bool | None
    elevator: bool | None
    accessible_toilet: bool | None
    raw: str | None
    source_id: str


@dataclass(frozen=True)
class PlaceRecord:
    """One ``places`` row plus its optional ``accessibility`` row.

    ``accessibility is None`` means there is no barrier-free row; the API reports grade UNKNOWN.
    IDs are strings at this boundary even though SQLite stores INTEGER (contract: opaque string).
    """
    id: str
    source_place_id: str | None
    name: str
    category: str
    area: str
    address: str | None
    latitude: float
    longitude: float
    indoor: bool | None
    open_hours: OpenHoursRecord
    price_level: int | None
    default_stay_min: int
    overview: str | None
    source_id: str
    updated_at: str
    accessibility: AccessibilityRecord | None = None

    @property
    def source_ids(self) -> tuple[str, ...]:
        """places.source_id ∪ accessibility.source_id, without duplicates, base source first (DEC-003)."""
        ids = [self.source_id]
        if self.accessibility is not None and self.accessibility.source_id not in ids:
            ids.append(self.accessibility.source_id)
        return tuple(ids)


@dataclass(frozen=True)
class DataSourceRecord:
    """One ``data_sources`` row (NFR-009). ``base_date`` = provider's reference date,
    ``retrieved_at`` = when we fetched it (contract Source.baseDate / retrievedAt)."""
    id: str
    provider: str
    dataset_name: str
    license: str | None
    url: str | None
    base_date: str | None
    retrieved_at: str


@dataclass(frozen=True)
class PlaceCandidate:
    """A radius-search hit. ``distance_m``: great-circle distance from the query center, meters."""
    place: PlaceRecord
    distance_m: float
