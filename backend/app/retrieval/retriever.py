"""PlaceRetriever — COMP-04 (FR-007, FR-008, AI-REQ-05, DEC-015, DEC-016, DEC-023).

Implements ``app.domain.course.CandidateRetriever``: hard filters only, then distance order
(scoring is out of scope, #22). Places are read only through ``PlaceRepository`` (DEC-005).

Hard conditions (a candidate must pass all of them):
1. area and walking radius from the area center (Repository query, DEC-001, DEC-023 ①)
2. excluded categories (Repository query, DEC-013)
3. not in the configured excluded-ID list (사후면세점 — DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19))
4. address present
5. opening hours: on the day of ``timeWindow`` an opening interval leaves room for the place's
   ``default_stay_min`` inside the window. ``open_hours`` NULL or that weekday missing = unknown
   (DEC-017, DEC-023 ③); never treated as always open.
6. mobility, per item (DEC-015, DEC-016 ③): WHEELCHAIR → ``wheelchair``, STROLLER → ``stroller``,
   INJURY → ``wheelchair`` (계단 회피 대리 지표). Only ``True`` passes. ``grade`` is not used.
   No accessibility row → every item is ``None``.
7. HARD indoor/outdoor preference (``candidate_violations`` checks it too).

A place that fails only because information is missing is reported in ``excluded_unknown_ids``
with the missing items in ``excluded_unknown_fields`` (contract ``excludedUnknown``, FR-013).
A place with any confirmed failure (closed, ``False``, excluded category, ...) is not counted
there, because including unknown information would not make it eligible.

Repository errors propagate (``RepositoryError``); an empty result means "no matching place".
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.courses.open_hours import opening_windows
from app.data.repository import PlaceRepository
from app.domain.course import RetrievalResult
from app.domain.place import PlaceCandidate, PlaceRecord
from app.retrieval.settings import RetrievalSettings, load_retrieval_settings

if TYPE_CHECKING:
    from app.api.profile_models import Profile

# excluded_unknown_fields values: "<항목>.<필드>" or a profile field name.
# 제안, 김영무 확인 대기. Same strings as ``app.courses.validator.candidate_violations``.
FIELD_ADDRESS = "address"
FIELD_OPEN_HOURS = "openHours"
FIELD_INDOOR = "indoorPreference"
MOBILITY_FIELDS = {"WHEELCHAIR": "wheelchair", "STROLLER": "stroller", "INJURY": "wheelchair"}


def mobility_field(item: str) -> str:
    return "mobility." + item


class PlaceRetriever:
    def __init__(self, repository: PlaceRepository, settings: RetrievalSettings | None = None):
        self._repository = repository
        self._settings = settings if settings is not None else load_retrieval_settings()

    def retrieve(self, profile: Profile) -> RetrievalResult:
        area = profile.area.value
        window = profile.timeWindow.value
        if area is None or window is None:
            raise ValueError("area and timeWindow are required for candidate search")
        center = self._settings.area_centers.get(area)
        if center is None:
            raise ValueError(f"no search center configured for area {area}")
        hits = self._repository.find_within_radius(
            center[0], center[1], self._settings.radius_m, area=area,
            exclude_categories=tuple(profile.excludedCategories.value or ()))
        items = _required_accessibility_items(profile.mobility.value)
        indoor = _required_indoor(profile)
        passed: list[PlaceCandidate] = []
        unknown_ids: set[str] = set()
        unknown_fields: set[str] = set()
        for hit in hits:
            if hit.place.id in self._settings.excluded_place_ids:
                continue
            rejected, unknown = check_place(hit.place, window.startAt, window.endAt, items, indoor)
            if rejected:
                continue
            if unknown:
                unknown_ids.add(hit.place.id)
                unknown_fields.update(unknown)
                continue
            passed.append(hit)
        passed.sort(key=lambda hit: (hit.distance_m, hit.place.id))
        return RetrievalResult(tuple(passed[:self._settings.max_candidates]),
                               frozenset(unknown_ids), frozenset(unknown_fields))


def check_place(place: PlaceRecord, start: datetime, end: datetime,
                accessibility_items: tuple[str, ...], indoor: bool | None) -> tuple[bool, set[str]]:
    """(confirmed failure, missing items) for conditions 4–7 of the module docstring."""
    rejected = False
    unknown: set[str] = set()
    if not place.address:
        unknown.add(FIELD_ADDRESS)
    fits, known = stay_fits(place, start, end)
    if not fits:
        if known:
            rejected = True
        else:
            unknown.add(FIELD_OPEN_HOURS)
    for item in accessibility_items:
        value = getattr(place.accessibility, item, None) if place.accessibility is not None else None
        if value is None:
            unknown.add(mobility_field(item))
        elif value is not True:
            rejected = True
    if indoor is not None:
        if place.indoor is None:
            unknown.add(FIELD_INDOOR)
        elif place.indoor is not indoor:
            rejected = True
    return rejected, unknown


def stay_fits(place: PlaceRecord, start: datetime, end: datetime) -> tuple[bool, bool]:
    """(an opening interval holds ``default_stay_min`` inside [start, end], weekday known).

    Uses the course engine's ``opening_windows`` so retrieval and validation read the stored
    intervals the same way (overnight intervals, ``24:00``, previous-day carry-over).
    """
    spans, known = opening_windows(place, start, end)
    stay = timedelta(minutes=place.default_stay_min)
    for opening, closing in spans:
        if min(closing, end) - max(opening, start) >= stay:
            return True, known
    return False, known


def _required_accessibility_items(mobility: list[str] | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(MOBILITY_FIELDS[item] for item in (mobility or ())))


def _required_indoor(profile: Profile) -> bool | None:
    preference = profile.indoorPreference
    if preference.strength == "HARD" and preference.value in ("INDOOR", "OUTDOOR"):
        return preference.value == "INDOOR"
    return None
