"""PlaceRepository interface — COMP-10 (FR-007, AI-REQ-01, NFR-009, DEC-003, DEC-005).

The course engine and retrieval use only this interface, never SQLite directly (DEC-005).
Draft pending agreement with 김영무 (issue #7 작업 A / #8 작업 A).

Failure rules shared by every implementation:
- Bad arguments raise ``ValueError``.
- Storage failures raise ``RepositoryError``. They are never turned into an empty list or ``None``.
- An empty list means "no matching place"; ``None`` from ``get_place`` means "no such ID".
"""
from collections.abc import Iterable
import math
from typing import Protocol, runtime_checkable

from app.domain.place import DataSourceRecord, PlaceCandidate, PlaceRecord


class RepositoryError(Exception):
    """Storage could not answer (DB missing, locked, corrupt, broken reference)."""


@runtime_checkable
class PlaceRepository(Protocol):
    def find_within_radius(self, center_lat: float, center_lon: float, radius_m: float, *,
                           area: str | None = None,
                           exclude_categories: Iterable[str] = (),
                           limit: int | None = None) -> list[PlaceCandidate]:
        """Places whose distance from the center is <= ``radius_m``.

        Units: WGS84 decimal degrees, meters. Sorted by distance, then place ID.
        ``area`` keeps only that area code (e.g. "HAEUNDAE"); ``exclude_categories`` drops
        those category values; ``limit`` caps the result (>= 1). The radius itself is chosen
        by the caller (setting, DEC-001), not by the repository.
        """
        ...

    def get_place(self, place_id: str) -> PlaceRecord | None:
        """One place with its accessibility row, or ``None`` if the ID does not exist."""
        ...

    def existing_place_ids(self, place_ids: Iterable[str]) -> frozenset[str]:
        """The subset of ``place_ids`` that exist in storage (CourseValidator, AI-REQ-01)."""
        ...

    def get_sources(self, source_ids: Iterable[str]) -> list[DataSourceRecord]:
        """Sources for the given IDs, in first-seen order without duplicates.

        A missing ID is a broken reference and raises ``RepositoryError``.
        """
        ...


def check_radius_query(center_lat: float, center_lon: float, radius_m: float,
                       limit: int | None) -> None:
    """Shared argument validation for ``find_within_radius``."""
    for name, value, low, high in (("center_lat", center_lat, -90.0, 90.0),
                                   ("center_lon", center_lon, -180.0, 180.0)):
        if not _is_number(value) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be a number in [{low}, {high}]")
    if not _is_number(radius_m) or not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError("radius_m must be a positive finite number of meters")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("limit must be a positive integer or None")


def check_categories(values: Iterable[str]) -> frozenset[str]:
    """``exclude_categories`` as a set of strings (see ``check_str_collection``)."""
    return frozenset(check_str_collection(values, "exclude_categories"))


def check_id(value: object, name: str = "place_id") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def check_id_list(values: Iterable[str], name: str = "place_ids") -> list[str]:
    """ID-list arguments (``existing_place_ids``, ``get_sources``) as a list of strings."""
    return check_str_collection(values, name)


def check_str_collection(values: object, name: str) -> list[str]:
    """A collection of strings, in order.

    A bare string is rejected because iterating it would split ``"10"`` into ``"1"``, ``"0"``.
    ``None``, non-iterables and non-string items raise ``ValueError`` (never ``TypeError``).
    """
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a collection of strings, not a single string")
    try:
        items = list(values)  # type: ignore[call-overload]
    except TypeError:
        raise ValueError(f"{name} must be a collection of strings") from None
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{name} must contain only strings")
    return items


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
