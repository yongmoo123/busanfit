"""Behavior every PlaceRepository must share. Subclass and implement ``make_repo``.

All places, sources and coordinates here are [가상] fixtures, not real Busan data.
Offsets are along a meridian, so the haversine distance equals the offset in meters.
"""
import math

import pytest

from app.data.geo import EARTH_RADIUS_M
from app.data.repository import PlaceRepository, RepositoryError
from app.domain.place import AccessibilityRecord, DataSourceRecord, OpenHoursRecord, PlaceRecord

CENTER = (35.16, 129.16)  # [가상] test center, not the area center (issue #7 "정할 것 1")
RADIUS_M = 1500.0


def north(meters: float) -> tuple[float, float]:
    return CENTER[0] + math.degrees(meters / EARTH_RADIUS_M), CENTER[1]


SOURCES = [
    DataSourceRecord("1", "[가상] 테스트 기관", "[가상] 기본 장소 데이터", None,
                     "https://example.invalid/busanfit/base", None, "2026-11-09T09:00:00+09:00"),
    DataSourceRecord("2", "[가상] 테스트 기관", "[가상] 무장애 데이터", "MOCK_ONLY",
                     "https://example.invalid/busanfit/access", "2026-11-01",
                     "2026-11-09T09:00:00+09:00"),
]

UNKNOWN_HOURS = OpenHoursRecord(parsed=None, text=None)


def place(place_id: str, meters_north: float, category: str, *, area: str = "HAEUNDAE",
          accessibility: AccessibilityRecord | None = None, **fields) -> PlaceRecord:
    lat, lon = north(meters_north)
    values = dict(source_place_id=f"mock-{place_id}", name=f"[가상] 장소 {place_id}",
                  category=category, area=area, address=None, latitude=lat, longitude=lon,
                  indoor=None, open_hours=UNKNOWN_HOURS, price_level=None, default_stay_min=60,
                  overview=None, source_id="1", updated_at="2026-11-09T09:00:00+09:00",
                  accessibility=accessibility)
    values.update(fields)
    return PlaceRecord(id=place_id, **values)


PLACES = [
    place("10", 100, "CAFE", address="[가상] 주소", indoor=True,
          open_hours=OpenHoursRecord({"mon": [{"open": "10:00", "close": "18:00"}]}, "[가상] 10:00~18:00"),
          price_level=2, overview="[가상] 개요",
          accessibility=AccessibilityRecord("VERIFIED", True, None, False, None,
                                            '{"mock": true}', "2")),
    place("11", 1490, "FOOD", default_stay_min=70),            # every optional field unknown
    place("12", 1510, "EXHIBITION"),                           # just outside 1.5 km
    place("13", -1000, "PARK",                                 # accessibility from same source
          accessibility=AccessibilityRecord("UNKNOWN", None, None, None, None, None, "1")),
    place("14", 500, "SHOPPING", area="SEOMYEON"),
    place("15", 300, "OTHER", open_hours=OpenHoursRecord(None, "[가상] 해석 불가 원문")),
]


class PlaceRepositoryContract:
    def make_repo(self, places, sources) -> PlaceRepository:
        raise NotImplementedError

    def make_failing_repo(self) -> PlaceRepository:
        """A repository whose storage fails on every call."""
        raise NotImplementedError

    @pytest.fixture
    def repo(self):
        return self.make_repo(PLACES, SOURCES)

    def ids(self, candidates):
        return [candidate.place.id for candidate in candidates]

    def test_satisfies_protocol(self, repo):
        assert isinstance(repo, PlaceRepository)

    def test_radius_boundary_and_order(self, repo):
        hits = repo.find_within_radius(*CENTER, RADIUS_M)
        assert self.ids(hits) == ["10", "15", "14", "13", "11"]
        assert "12" not in self.ids(hits)
        assert hits[-1].distance_m == pytest.approx(1490, abs=0.01)
        assert [hit.distance_m for hit in hits] == sorted(hit.distance_m for hit in hits)

    def test_area_and_category_filters(self, repo):
        hits = repo.find_within_radius(*CENTER, RADIUS_M, area="HAEUNDAE",
                                       exclude_categories={"CAFE", "PARK"})
        assert self.ids(hits) == ["15", "11"]

    def test_limit(self, repo):
        assert self.ids(repo.find_within_radius(*CENTER, RADIUS_M, limit=2)) == ["10", "15"]

    def test_no_candidates_is_empty_list(self, repo):
        assert repo.find_within_radius(-35.0, -129.0, 10) == []

    @pytest.mark.parametrize("args, kwargs", [
        ((91, 129.16, 1500), {}), ((35.16, 181, 1500), {}), ((35.16, 129.16, 0), {}),
        ((35.16, 129.16, -1), {}), ((35.16, 129.16, math.nan), {}),
        ((35.16, 129.16, math.inf), {}), ((35.16, 129.16, True), {}),
        (("35.16", 129.16, 1500), {}), ((35.16, 129.16, 1500), {"limit": 0}),
        ((35.16, 129.16, 1500), {"limit": True}),
        ((35.16, 129.16, 1500), {"exclude_categories": "CAFE"}),
        ((35.16, 129.16, 1500), {"exclude_categories": None}),
        ((35.16, 129.16, 1500), {"exclude_categories": [[]]}),
        ((35.16, 129.16, 1500), {"exclude_categories": [1]}),
    ])
    def test_invalid_query_raises_value_error(self, repo, args, kwargs):
        with pytest.raises(ValueError):
            repo.find_within_radius(*args, **kwargs)

    def test_unknown_values_stay_none(self, repo):
        found = repo.get_place("11")
        assert (found.address, found.indoor, found.price_level, found.overview) == (None,) * 4
        assert found.open_hours == UNKNOWN_HOURS
        assert found.accessibility is None
        assert found.default_stay_min == 70

    def test_unparsed_open_hours_keep_text(self, repo):
        assert repo.get_place("15").open_hours == OpenHoursRecord(None, "[가상] 해석 불가 원문")

    def test_known_fields_and_partial_accessibility(self, repo):
        found = repo.get_place("10")
        assert found == PLACES[0]
        assert found.indoor is True and found.price_level == 2
        access = found.accessibility
        assert (access.wheelchair, access.stroller, access.elevator, access.accessible_toilet) \
            == (True, None, False, None)

    def test_source_ids_merged_without_duplicates(self, repo):
        assert repo.get_place("10").source_ids == ("1", "2")
        assert repo.get_place("13").source_ids == ("1",)
        assert repo.get_place("11").source_ids == ("1",)

    def test_get_place_missing_and_bad_id(self, repo):
        assert repo.get_place("999") is None
        with pytest.raises(ValueError):
            repo.get_place(10)

    def test_existing_place_ids(self, repo):
        assert repo.existing_place_ids(["10", "999", "11", "10"]) == frozenset({"10", "11"})
        assert repo.existing_place_ids([]) == frozenset()

    def test_get_sources(self, repo):
        assert [s.id for s in repo.get_sources(["2", "1", "2"])] == ["2", "1"]
        assert repo.get_sources(["1"])[0] == SOURCES[0]
        with pytest.raises(RepositoryError):
            repo.get_sources(["1", "999"])

    @pytest.mark.parametrize("bad", ["10", b"10", None, 10, [10], [None], [["10"]]])
    @pytest.mark.parametrize("method", ["existing_place_ids", "get_sources"])
    def test_id_list_rejects_bare_string_and_non_strings(self, repo, method, bad):
        # A bare "10" must not be read as the IDs "1" and "0" (review on PR #15).
        with pytest.raises(ValueError):
            getattr(repo, method)(bad)

    def test_results_are_isolated_from_callers(self):
        def hours():
            return OpenHoursRecord({"mon": [{"open": "10:00", "close": "18:00"}]}, "[가상] 10:00~18:00")

        given = place("20", 100, "CAFE", open_hours=hours())
        repo = self.make_repo([given], SOURCES)
        given.open_hours.parsed["mon"][0]["open"] = "00:00"  # caller mutates the record it passed in
        repo.get_place("20").open_hours.parsed["mon"][0]["open"] = "01:00"
        repo.find_within_radius(*CENTER, RADIUS_M)[0].place.open_hours.parsed["mon"].clear()
        expected = hours()
        assert repo.get_place("20").open_hours == expected
        assert repo.find_within_radius(*CENTER, RADIUS_M)[0].place.open_hours == expected

    @pytest.mark.parametrize("call", [
        lambda r: r.find_within_radius(*CENTER, RADIUS_M),
        lambda r: r.get_place("10"),
        lambda r: r.existing_place_ids(["10"]),
        lambda r: r.get_sources(["1"]),
    ])
    def test_storage_failure_raises_not_empty(self, call):
        with pytest.raises(RepositoryError):
            call(self.make_failing_repo())
