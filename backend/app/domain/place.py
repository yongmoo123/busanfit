"""Place records shared by the course engine and PlaceRepository (FR-007, DEC-003, DEC-005).

Plain data only: no DB, HTTP or LLM imports. Field names mirror the columns of
``backend/app/data/schema.sql`` (SDD 5.2); API JSON (camelCase) is converted in ``app.api``.

Unknown stays unknown: ``None`` is never turned into "free", "accessible", "always open" or 0.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

# Contract (openapi Place.category) values, shared by DB, API and UI (DEC-013).
CONTRACT_CATEGORIES = ("CAFE", "FOOD", "EXHIBITION", "ATTRACTION", "PARK", "SHOPPING", "OTHER")

ACCESSIBILITY_GRADES = ("VERIFIED", "UNKNOWN", "UNSUITABLE")


WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HH_MM = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
END_OF_DAY = "24:00"  # allowed only as ``close``


@dataclass(frozen=True)
class OpenHoursRecord:
    """Opening hours as stored.

    ``parsed``: normalized structure (``places.open_hours`` JSON) or ``None`` when absent or
    not parseable. ``text``: original text from the source (``places.open_hours_text``) or
    ``None``. ``text`` present but ``parsed`` ``None`` means "known to the user, unverified for
    HARD checks".

    Shape of ``parsed`` — 이찬용 제안(임시), 김영무 확인 대기 (PR #15 review, issue #7 가정 6)::

        {"mon": [{"open": "09:00", "close": "18:00"}], "tue": [], ...}

    - Keys: ``mon``..``sun``. A missing key = that day is unknown; ``[]`` = closed (confirmed).
    - Several intervals per day are allowed. Times are 24-hour ``"HH:mm"``, Asia/Seoul.
    - ``close < open`` means the interval ends the next day (e.g. 18:00→02:00) and is stored
      under the day it starts.
    - ``"24:00"`` is allowed only as ``close`` and means "until the end of that day".
      Open 24 hours = ``{"open": "00:00", "close": "24:00"}``. ``"24:00"`` as ``open`` is an error.
    - ``{}`` (every day unknown) is an error: use ``parsed = None`` (NULL) instead.
    - Unparseable source text: ``parsed`` is ``None`` and the text stays in ``text`` only.
    - Holidays are out of scope and kept only in ``text``.
    ``validate_open_hours`` checks only day keys, ``"HH:mm"`` format and ``open != close``
    (plus the two rules above).
    """
    parsed: Mapping[str, Any] | None
    text: str | None


def validate_open_hours(parsed: object) -> None:
    """Raise ``ValueError`` if ``parsed`` does not follow the proposed shape above.

    Checks only: day keys, ``"HH:mm"`` format (00:00–23:59, and ``"24:00"`` for ``close`` only),
    ``open != close``, and that the object is not empty (all-unknown must be ``None``).
    No overlap check and no "open at time t" logic (not agreed yet).
    """
    if not isinstance(parsed, Mapping):
        raise ValueError("open_hours must be an object keyed by weekday")
    if not parsed:
        raise ValueError("open_hours must not be empty; use None (NULL) when every day is unknown")
    for day, intervals in parsed.items():
        if day not in WEEKDAY_KEYS:
            raise ValueError(f"open_hours: unknown weekday key {day!r}")
        if not isinstance(intervals, (list, tuple)):
            raise ValueError(f"open_hours[{day!r}] must be a list of intervals")
        for interval in intervals:
            if not isinstance(interval, Mapping) or set(interval) != {"open", "close"}:
                raise ValueError(f"open_hours[{day!r}]: interval must have exactly open and close")
            for name in ("open", "close"):
                value = interval[name]
                if name == "close" and value == END_OF_DAY:
                    continue
                if not isinstance(value, str) or not _HH_MM.fullmatch(value):
                    allowed = "'HH:mm' (00:00-23:59, or 24:00)" if name == "close" \
                        else "'HH:mm' (00:00-23:59; 24:00 only as close)"
                    raise ValueError(f"open_hours[{day!r}].{name} must be {allowed}, got {value!r}")
            if interval["open"] == interval["close"]:
                raise ValueError(f"open_hours[{day!r}]: open and close must differ")


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
    ``id`` is the opaque string the API exposes. It must survive a reload of the DB, so it is based
    on ``source_place_id`` and is not the integer ``places.id`` (DEC-017).
    ``price_amount`` is in won, ``price_basis`` is ``PER_PERSON`` or ``TOTAL``, ``price_text`` is the
    original text. Sprint 2 stores only the text; ``None`` never means free (DEC-014).
    """
    id: str
    source_place_id: str
    name: str
    category: str
    area: str
    address: str | None
    latitude: float
    longitude: float
    indoor: bool | None
    open_hours: OpenHoursRecord
    price_amount: int | None
    price_basis: str | None
    price_text: str | None
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
    url: str
    base_date: str | None
    retrieved_at: str


@dataclass(frozen=True)
class PlaceCandidate:
    """A radius-search hit. ``distance_m``: great-circle distance from the query center, meters."""
    place: PlaceRecord
    distance_m: float
