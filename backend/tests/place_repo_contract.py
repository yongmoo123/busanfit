"""Behavior every PlaceRepository must share. Subclass and implement ``make_repo``.

All places, sources and coordinates here are [가상] fixtures, not real Busan data.
Offsets are along a meridian, so the haversine distance equals the offset in meters.
"""
import math
import re

import pytest

from app.data.geo import EARTH_RADIUS_M, bounding_box, haversine_m
from app.data.place_id import parse_place_id
from app.data.repository import PlaceRepository, RepositoryError
from app.domain.place import AccessibilityRecord, DataSourceRecord, OpenHoursRecord, PlaceRecord

CENTER = (35.16, 129.16)  # [가상] test center, not the area center (issue #7 "정할 것 1")
RADIUS_M = 1500.0


def north(meters: float) -> tuple[float, float]:
    return CENTER[0] + math.degrees(meters / EARTH_RADIUS_M), CENTER[1]


def east(meters: float, lat: float = CENTER[0]) -> tuple[float, float]:
    """Point on the same latitude whose haversine distance from (lat, CENTER lon) is ``meters``."""
    dlon = 2 * math.asin(math.sin(meters / (2 * EARTH_RADIUS_M)) / math.cos(math.radians(lat)))
    return lat, CENTER[1] + math.degrees(dlon)


SOURCES = [
    DataSourceRecord("1", "mock-base", "[가상] 테스트 기관", "[가상] 기본 장소 데이터", None,
                     "https://example.invalid/busanfit/base", None, "2026-11-09T09:00:00+09:00"),
    DataSourceRecord("2", "mock-access", "[가상] 테스트 기관", "[가상] 무장애 데이터", "MOCK_ONLY",
                     "https://example.invalid/busanfit/access", "2026-11-01",
                     "2026-11-09T09:00:00+09:00"),
]

UNKNOWN_HOURS = OpenHoursRecord(parsed=None, text=None)

# API place.id = "{data_sources.code}:{source_place_id}" (DEC-017, app.data.place_id)
PLACE_ID_FORMAT = re.compile(r"[a-z0-9-]+:[^/]+")


def pid(key: str) -> str:
    """API place.id of the fixture ``place(key, ...)`` (base source code "mock-base")."""
    return f"mock-base:{key}"


def place(key: str, meters_north: float, category: str, *, area: str = "HAEUNDAE",
          accessibility: AccessibilityRecord | None = None, **fields) -> PlaceRecord:
    lat, lon = north(meters_north)
    values = dict(source_code="mock-base", source_place_id=key, name=f"[가상] 장소 {key}",
                  category=category, area=area, address=None, latitude=lat, longitude=lon,
                  indoor=None, open_hours=UNKNOWN_HOURS, price_amount=None, price_basis=None,
                  price_text=None, default_stay_min=60, overview=None, source_id="1", updated_at="2026-11-09T09:00:00+09:00",
                  accessibility=accessibility)
    values.update(fields)
    return PlaceRecord(**values)


PLACES = [
    place("10", 100, "CAFE", address="[가상] 주소", indoor=True,
          open_hours=OpenHoursRecord({"mon": [{"open": "10:00", "close": "18:00"}]}, "[가상] 10:00~18:00"),
          price_amount=5000, price_basis="PER_PERSON", price_text="[가상] 1인 5,000원",
          overview="[가상] 개요",
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
        assert self.ids(hits) == [pid(k) for k in ("10", "15", "14", "13", "11")]
        assert pid("12") not in self.ids(hits)
        assert hits[-1].distance_m == pytest.approx(1490, abs=0.01)
        assert [hit.distance_m for hit in hits] == sorted(hit.distance_m for hit in hits)

    def test_area_and_category_filters(self, repo):
        hits = repo.find_within_radius(*CENTER, RADIUS_M, area="HAEUNDAE",
                                       exclude_categories={"CAFE", "PARK"})
        assert self.ids(hits) == [pid("15"), pid("11")]

    def test_limit(self, repo):
        assert self.ids(repo.find_within_radius(*CENTER, RADIUS_M, limit=2)) == [pid("10"), pid("15")]

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
        found = repo.get_place(pid("11"))
        assert (found.address, found.indoor, found.price_amount, found.price_basis,
                found.price_text, found.overview) == (None,) * 6
        assert found.open_hours == UNKNOWN_HOURS
        assert found.accessibility is None
        assert found.default_stay_min == 70

    def test_unparsed_open_hours_keep_text(self, repo):
        assert repo.get_place(pid("15")).open_hours == OpenHoursRecord(None, "[가상] 해석 불가 원문")

    def test_known_fields_and_partial_accessibility(self, repo):
        found = repo.get_place(pid("10"))
        assert found == PLACES[0]
        assert found.indoor is True
        assert (found.price_amount, found.price_basis, found.price_text) \
            == (5000, "PER_PERSON", "[가상] 1인 5,000원")
        access = found.accessibility
        assert (access.wheelchair, access.stroller, access.elevator, access.accessible_toilet) \
            == (True, None, False, None)

    def test_source_ids_merged_without_duplicates(self, repo):
        assert repo.get_place(pid("10")).source_ids == ("1", "2")
        assert repo.get_place(pid("13")).source_ids == ("1",)
        assert repo.get_place(pid("11")).source_ids == ("1",)

    def test_get_place_missing_and_bad_id(self, repo):
        assert repo.get_place(pid("999")) is None
        with pytest.raises(ValueError):
            repo.get_place(10)

    def test_existing_place_ids(self, repo):
        assert repo.existing_place_ids([pid("10"), pid("999"), pid("11"), pid("10")]) \
            == frozenset({pid("10"), pid("11")})
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
        repo.get_place(pid("20")).open_hours.parsed["mon"][0]["open"] = "01:00"
        repo.find_within_radius(*CENTER, RADIUS_M)[0].place.open_hours.parsed["mon"].clear()
        expected = hours()
        assert repo.get_place(pid("20")).open_hours == expected
        assert repo.find_within_radius(*CENTER, RADIUS_M)[0].place.open_hours == expected

    @pytest.mark.parametrize("call", [
        lambda r: r.find_within_radius(*CENTER, RADIUS_M),
        lambda r: r.get_place(pid("10")),
        lambda r: r.existing_place_ids([pid("10")]),
        lambda r: r.get_sources(["1"]),
    ])
    def test_storage_failure_raises_not_empty(self, call):
        with pytest.raises(RepositoryError):
            call(self.make_failing_repo())

    def test_place_ids_follow_source_code_rule(self, repo):
        """Every returned place.id is "{data_sources.code}:{source_place_id}" (DEC-017)."""
        codes = {source.id: source.code for source in SOURCES}
        found = [hit.place for hit in repo.find_within_radius(*CENTER, 10_000)]
        assert len(found) == len(PLACES)
        for record in found:
            assert PLACE_ID_FORMAT.fullmatch(record.id), record.id
            assert record.id == f"{codes[record.source_id]}:{record.source_place_id}"
            assert parse_place_id(record.id) == (codes[record.source_id], record.source_place_id)
            assert repo.get_place(record.id) == record
        assert repo.existing_place_ids([p.id for p in PLACES]) == frozenset(p.id for p in PLACES)

    def test_place_id_independent_of_load_order(self):
        reloaded = self.make_repo(PLACES[::-1], SOURCES[::-1])
        assert [hit.place.id for hit in reloaded.find_within_radius(*CENTER, RADIUS_M)] \
            == [pid(k) for k in ("10", "15", "14", "13", "11")]

    @pytest.mark.parametrize("bad", [
        "10", "mock-base", "mock-base:", ":10", "MOCK-BASE:10", "mock-base:10/x", "",
        # URL-unsafe or out-of-rule original IDs (source_place_id = [A-Za-z0-9_-]{1,64})
        "mock-base:10?x", "mock-base:10#x", "mock-base:10%x", "mock-base:10%2Fx",
        "mock-base:1%30", "mock-base:10 x", "mock-base:10.5", "mock-base:장소",
        "mock-base:" + "1" * 65, "mock-base:10:x",
    ])
    def test_malformed_place_id_is_not_found(self, repo, bad):
        assert repo.get_place(bad) is None
        assert repo.existing_place_ids([bad]) == frozenset()

    def test_unsafe_original_id_cannot_become_a_place(self):
        # The record itself refuses it, so no implementation can store or return such an ID.
        for bad in ["10?x", "10#x", "10%2F", "10%61", "a/b", "a b", "", "a" * 65, "한글"]:
            with pytest.raises(ValueError):
                place("x", 100, "CAFE", source_place_id=bad)

    def test_allowed_original_id_mix_round_trips(self):
        keys = ["126508", "Mock_ID-01", "a" * 64, "_", "-"]
        repo = self.make_repo([place(key, 100 + i, "CAFE") for i, key in enumerate(keys)],
                              SOURCES)
        for key in keys:
            found = repo.get_place(pid(key))
            assert found is not None and found.id == pid(key)
            assert parse_place_id(found.id) == ("mock-base", key)
        assert repo.existing_place_ids([pid(key) for key in keys]) \
            == frozenset(pid(key) for key in keys)

    def test_same_original_id_from_two_sources_are_two_places(self):
        other = place("10", 200, "CAFE", source_code="mock-access", source_id="2")
        repo = self.make_repo([PLACES[0], other], SOURCES)
        assert repo.existing_place_ids([pid("10"), "mock-access:10"]) \
            == frozenset({pid("10"), "mock-access:10"})

    # --- radius search geometry (work D). All coordinates are fixed [가상] offsets. ---

    def at(self, key, lat_lon, category="CAFE"):
        lat, lon = lat_lon
        return place(key, 0, category, latitude=lat, longitude=lon)

    def test_radius_boundary_along_parallel(self):
        # East–west needs the cos(latitude) correction of the box width: without it the
        # 1,490 m point east would fall outside the box and be lost.
        repo = self.make_repo([self.at("e1490", east(1490)), self.at("e1510", east(1510)),
                               self.at("w1490", east(-1490)), self.at("w1510", east(-1510))],
                              SOURCES)
        hits = repo.find_within_radius(*CENTER, RADIUS_M)
        assert sorted(self.ids(hits)) == [pid("e1490"), pid("w1490")]
        assert [hit.distance_m for hit in hits] == pytest.approx([1490, 1490], abs=0.01)

    def test_box_corner_outside_circle_excluded(self):
        box = bounding_box(*CENTER, RADIUS_M)
        corner = (CENTER[0] + 0.95 * (box.max_lat - CENTER[0]),
                  CENTER[1] + 0.95 * (box.max_lon - CENTER[1]))
        diagonal_inside = (north(900)[0], east(900)[1])
        assert box.contains(*corner) and haversine_m(*CENTER, *corner) > RADIUS_M
        assert haversine_m(*CENTER, *diagonal_inside) < RADIUS_M
        repo = self.make_repo([self.at("corner", corner), self.at("inside", diagonal_inside)],
                              SOURCES)
        assert self.ids(repo.find_within_radius(*CENTER, RADIUS_M)) == [pid("inside")]

    def test_null_hours_price_accessibility_stay_none(self, repo):
        unknown = repo.get_place(pid("11"))
        assert unknown.open_hours == OpenHoursRecord(None, None)
        assert (unknown.price_amount, unknown.price_basis, unknown.price_text) == (None,) * 3
        assert unknown.accessibility is None
        text_only = repo.get_place(pid("15")).open_hours
        assert (text_only.parsed, text_only.text) == (None, "[가상] 해석 불가 원문")
        items = repo.get_place(pid("13")).accessibility
        assert (items.grade, items.wheelchair, items.stroller, items.elevator,
                items.accessible_toilet, items.raw) == ("UNKNOWN", None, None, None, None, None)
        partial = repo.get_place(pid("10")).accessibility
        assert (partial.stroller, partial.accessible_toilet) == (None, None)  # not False

    def test_same_base_and_access_source_merged_into_one(self, repo):
        found = repo.get_place(pid("13"))
        assert found.source_id == found.accessibility.source_id == "1"
        assert found.source_ids == ("1",)
        assert [source.id for source in repo.get_sources(found.source_ids)] == ["1"]
