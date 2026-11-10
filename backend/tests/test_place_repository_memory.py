"""InMemoryPlaceRepository against the shared PlaceRepository contract ([가상] data only)."""
from dataclasses import replace

import pytest

from app.data.memory import InMemoryPlaceRepository
from app.data.repository import RepositoryError
from app.domain.place import AccessibilityRecord
from place_repo_contract import PLACES, SOURCES, PlaceRepositoryContract, place


class TestInMemoryPlaceRepository(PlaceRepositoryContract):
    def make_repo(self, places, sources):
        return InMemoryPlaceRepository(places, sources)

    def make_failing_repo(self):
        return InMemoryPlaceRepository(PLACES, SOURCES, error=RepositoryError("[가상] storage down"))


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        InMemoryPlaceRepository([PLACES[0], PLACES[0]], SOURCES)
    with pytest.raises(ValueError):
        InMemoryPlaceRepository(PLACES, [SOURCES[0], SOURCES[0]])


def test_duplicate_source_code_rejected():
    # data_sources.code is UNIQUE in schema.sql (#16)
    with pytest.raises(ValueError, match="code"):
        InMemoryPlaceRepository([], [SOURCES[0], replace(SOURCES[1], code=SOURCES[0].code)])


@pytest.mark.parametrize("fields", [
    {"source_code": "mock-access"},                 # not the code of source_id "1"
    {"source_id": "999"},                           # unknown source
    {"accessibility": AccessibilityRecord("UNKNOWN", None, None, None, None, None, "999")},
])
def test_place_must_match_its_source(fields):
    with pytest.raises(ValueError):
        InMemoryPlaceRepository([place("30", 100, "CAFE", **fields)], SOURCES)


@pytest.mark.parametrize("fields", [
    {"source_code": "Mock-Base"}, {"source_code": "mock:base"}, {"source_code": ""},
    {"source_place_id": ""}, {"source_place_id": "a/b"}, {"source_place_id": None},
])
def test_record_rejects_unsafe_id_parts(fields):
    with pytest.raises(ValueError):
        place("30", 100, "CAFE", **fields)


@pytest.mark.parametrize("code", ["Mock", "mock:x", "", "mock_x"])
def test_source_record_rejects_unsafe_code(code):
    with pytest.raises(ValueError):
        replace(SOURCES[0], code=code)


def test_place_id_is_code_and_original_id():
    record = place("30", 100, "CAFE", source_place_id="126508")
    assert record.id == "mock-base:126508"
    assert replace(record, source_code="mock-access").id == "mock-access:126508"
