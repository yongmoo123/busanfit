"""SQLite PlaceRepository — COMP-10 (FR-007, NFR-001, DEC-003, DEC-005, DEC-017).

Radius search: (1) SQL bounding box on ``latitude``/``longitude`` using ``idx_places_lat_lon``,
(2) haversine distance in Python. Rows are turned into new record objects on every call, so a
caller can never change what later calls return.

Failure rules (same as every implementation, see ``app.data.repository``):
- bad arguments → ``ValueError`` (checked before touching the DB)
- any ``sqlite3.Error`` (missing table, closed connection, locked/corrupt file) or a stored row
  that breaks the record rules → ``RepositoryError``; never an empty list or ``None``.
"""
from collections.abc import Iterable, Iterator, Sequence
import json
import sqlite3
from typing import Any

from app.data.geo import bounding_box, haversine_m
from app.data.place_id import make_place_id, parse_place_id
from app.data.repository import (RepositoryError, check_categories, check_id, check_id_list,
                                 check_radius_query)
from app.domain.place import (AccessibilityRecord, DataSourceRecord, OpenHoursRecord,
                              PlaceCandidate, PlaceRecord, validate_open_hours)

_PLACE_COLUMNS = """
    p.source_place_id, p.name, p.category, p.area, p.address, p.latitude, p.longitude,
    p.indoor, p.open_hours, p.open_hours_text, p.price_amount, p.price_basis, p.price_text,
    p.default_stay_min, p.overview, p.source_id, p.updated_at,
    s.code AS source_code,
    a.place_id AS a_place_id, a.grade AS a_grade, a.wheelchair AS a_wheelchair,
    a.stroller AS a_stroller, a.elevator AS a_elevator,
    a.accessible_toilet AS a_accessible_toilet, a.raw AS a_raw, a.source_id AS a_source_id
"""
_PLACE_FROM = """
    FROM places AS p
    JOIN data_sources AS s ON s.id = p.source_id
    LEFT JOIN accessibility AS a ON a.place_id = p.id
"""

# First step of the radius search. Extra conditions are appended by ``_box_query``.
BOX_SQL = (f"SELECT {_PLACE_COLUMNS} {_PLACE_FROM}"
           " WHERE p.latitude BETWEEN ? AND ? AND p.longitude BETWEEN ? AND ?")

_PLACE_BY_ID_SQL = (f"SELECT {_PLACE_COLUMNS} {_PLACE_FROM}"
                    " WHERE s.code = ? AND p.source_place_id = ?")

_SOURCE_SQL = ("SELECT id, code, provider, dataset_name, license, url, base_date, retrieved_at"
               " FROM data_sources WHERE id = ?")

# Pairs per IN (VALUES ...) query; 2 parameters each, well under SQLite's 999-variable floor.
_ID_BATCH = 400


class SqlitePlaceRepository:
    """PlaceRepository over an open SQLite connection (see ``app.data.db.connect``).

    The connection belongs to the caller, who also closes it. The repository only reads.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def find_within_radius(self, center_lat: float, center_lon: float, radius_m: float, *,
                           area: str | None = None,
                           exclude_categories: Iterable[str] = (),
                           limit: int | None = None) -> list[PlaceCandidate]:
        check_radius_query(center_lat, center_lon, radius_m, limit)
        excluded = check_categories(exclude_categories)
        if area is not None and not isinstance(area, str):
            raise ValueError("area must be a string or None")
        sql, params = _box_query(center_lat, center_lon, radius_m, area, excluded)
        hits = []
        for place in self._places(sql, params):
            distance = haversine_m(center_lat, center_lon, place.latitude, place.longitude)
            if distance <= radius_m:
                hits.append(PlaceCandidate(place, distance))
        hits.sort(key=lambda hit: (hit.distance_m, hit.place.id))
        return hits if limit is None else hits[:limit]

    def get_place(self, place_id: str) -> PlaceRecord | None:
        check_id(place_id)
        try:
            code, source_place_id = parse_place_id(place_id)
        except ValueError:
            return None  # a string that is not a place ID names no place (API 404)
        found = list(self._places(_PLACE_BY_ID_SQL, (code, source_place_id)))
        return found[0] if found else None

    def existing_place_ids(self, place_ids: Iterable[str]) -> frozenset[str]:
        pairs = []
        for place_id in check_id_list(place_ids, "place_ids"):
            try:
                pairs.append(parse_place_id(place_id))
            except ValueError:
                continue
        pairs = list(dict.fromkeys(pairs))
        found: set[str] = set()
        for start in range(0, len(pairs), _ID_BATCH):
            batch = pairs[start:start + _ID_BATCH]
            values = ", ".join("(?, ?)" for _ in batch)
            sql = ("SELECT s.code, p.source_place_id FROM places AS p"
                   " JOIN data_sources AS s ON s.id = p.source_id"
                   f" WHERE (s.code, p.source_place_id) IN (VALUES {values})")
            params = [value for pair in batch for value in pair]
            for row in self._fetch(sql, params):
                found.add(make_place_id(row["code"], row["source_place_id"]))
        return frozenset(found)

    def get_sources(self, source_ids: Iterable[str]) -> list[DataSourceRecord]:
        ids = list(dict.fromkeys(check_id_list(source_ids, "source_ids")))
        sources, missing = [], []
        for source_id in ids:
            rows = self._fetch(_SOURCE_SQL, (source_id,)) if source_id.isdecimal() else []
            if not rows:
                missing.append(source_id)
                continue
            sources.append(_convert(_source_record, rows[0]))
        if missing:
            raise RepositoryError(f"unknown source ids: {missing}")
        return sources

    def _fetch(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        """Rows as plain dicts, whatever ``row_factory`` the caller's connection uses."""
        try:
            cursor = self._conn.execute(sql, params)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        except sqlite3.Error as error:
            raise RepositoryError(f"SQLite query failed: {type(error).__name__}") from error

    def _places(self, sql: str, params: Sequence[Any]) -> Iterator[PlaceRecord]:
        for row in self._fetch(sql, params):
            yield _convert(_place_record, row)


def _box_query(lat: float, lon: float, radius_m: float, area: str | None,
               excluded: frozenset[str]) -> tuple[str, list[Any]]:
    box = bounding_box(lat, lon, radius_m)
    sql = BOX_SQL
    params: list[Any] = [box.min_lat, box.max_lat, box.min_lon, box.max_lon]
    if area is not None:
        sql += " AND p.area = ?"
        params.append(area)
    if excluded:
        sql += f" AND p.category NOT IN ({', '.join('?' for _ in excluded)})"
        params.extend(sorted(excluded))
    return sql, params


def _convert(builder, row):
    """Build a record from a stored row; a row that breaks the record rules is a storage error."""
    try:
        return builder(row)
    except (ValueError, TypeError, KeyError) as error:
        raise RepositoryError(f"stored row is invalid: {error}") from error


def _bool(value: int | None) -> bool | None:
    """0/1/NULL → False/True/None. NULL stays None (unknown is never False)."""
    if value is None:
        return None
    if value not in (0, 1):
        raise ValueError(f"boolean column holds {value!r}")
    return bool(value)


def _open_hours(parsed_json: str | None, text: str | None) -> OpenHoursRecord:
    if parsed_json is None:
        return OpenHoursRecord(None, text)
    parsed = json.loads(parsed_json)
    validate_open_hours(parsed)
    return OpenHoursRecord(parsed, text)


def _place_record(row: dict[str, Any]) -> PlaceRecord:
    accessibility = None
    if row["a_place_id"] is not None:
        accessibility = AccessibilityRecord(
            grade=row["a_grade"], wheelchair=_bool(row["a_wheelchair"]),
            stroller=_bool(row["a_stroller"]), elevator=_bool(row["a_elevator"]),
            accessible_toilet=_bool(row["a_accessible_toilet"]), raw=row["a_raw"],
            source_id=str(row["a_source_id"]))
    return PlaceRecord(
        source_code=row["source_code"], source_place_id=row["source_place_id"],
        name=row["name"], category=row["category"], area=row["area"], address=row["address"],
        latitude=row["latitude"], longitude=row["longitude"], indoor=_bool(row["indoor"]),
        open_hours=_open_hours(row["open_hours"], row["open_hours_text"]),
        price_amount=row["price_amount"], price_basis=row["price_basis"],
        price_text=row["price_text"], default_stay_min=row["default_stay_min"],
        overview=row["overview"], source_id=str(row["source_id"]),
        updated_at=row["updated_at"], accessibility=accessibility)


def _source_record(row: dict[str, Any]) -> DataSourceRecord:
    return DataSourceRecord(
        id=str(row["id"]), code=row["code"], provider=row["provider"],
        dataset_name=row["dataset_name"], license=row["license"], url=row["url"],
        base_date=row["base_date"], retrieved_at=row["retrieved_at"])
