"""In-memory PlaceRepository for tests of the course engine (not for real data)."""
from collections.abc import Iterable
from copy import deepcopy

from app.data.geo import haversine_m
from app.data.repository import (RepositoryError, check_categories, check_id, check_id_list,
                                 check_radius_query)
from app.domain.place import DataSourceRecord, PlaceCandidate, PlaceRecord


class InMemoryPlaceRepository:
    """Holds given records; behaves like the SQLite implementation.

    Records are deep-copied when stored and when returned, so mutating nested values
    (e.g. ``open_hours.parsed``) in the caller never changes what later calls return —
    the same isolation a DB gives by building new objects per query.

    ``error``: when set, every call raises it, to test "DB failure is not an empty list".
    """

    def __init__(self, places: Iterable[PlaceRecord] = (), sources: Iterable[DataSourceRecord] = (),
                 *, error: RepositoryError | None = None):
        self._places: dict[str, PlaceRecord] = {}
        for place in places:
            if place.id in self._places:
                raise ValueError(f"duplicate place id {place.id!r}")
            self._places[place.id] = deepcopy(place)
        self._sources: dict[str, DataSourceRecord] = {}
        for source in sources:
            if source.id in self._sources:
                raise ValueError(f"duplicate source id {source.id!r}")
            self._sources[source.id] = source
        self.error = error

    def find_within_radius(self, center_lat: float, center_lon: float, radius_m: float, *,
                           area: str | None = None,
                           exclude_categories: Iterable[str] = (),
                           limit: int | None = None) -> list[PlaceCandidate]:
        check_radius_query(center_lat, center_lon, radius_m, limit)
        excluded = check_categories(exclude_categories)
        self._raise_if_failing()
        hits = []
        for place in self._places.values():
            if area is not None and place.area != area:
                continue
            if place.category in excluded:
                continue
            distance = haversine_m(center_lat, center_lon, place.latitude, place.longitude)
            if distance <= radius_m:
                hits.append(PlaceCandidate(place, distance))
        hits.sort(key=lambda hit: (hit.distance_m, hit.place.id))
        if limit is not None:
            hits = hits[:limit]
        return [PlaceCandidate(deepcopy(hit.place), hit.distance_m) for hit in hits]

    def get_place(self, place_id: str) -> PlaceRecord | None:
        check_id(place_id)
        self._raise_if_failing()
        found = self._places.get(place_id)
        return None if found is None else deepcopy(found)

    def existing_place_ids(self, place_ids: Iterable[str]) -> frozenset[str]:
        ids = check_id_list(place_ids, "place_ids")
        self._raise_if_failing()
        return frozenset(place_id for place_id in ids if place_id in self._places)

    def get_sources(self, source_ids: Iterable[str]) -> list[DataSourceRecord]:
        ids = list(dict.fromkeys(check_id_list(source_ids, "source_ids")))
        self._raise_if_failing()
        missing = [source_id for source_id in ids if source_id not in self._sources]
        if missing:
            raise RepositoryError(f"unknown source ids: {missing}")
        return [self._sources[source_id] for source_id in ids]

    def _raise_if_failing(self) -> None:
        if self.error is not None:
            raise self.error
