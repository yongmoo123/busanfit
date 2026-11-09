"""InMemoryPlaceRepository against the shared PlaceRepository contract ([가상] data only)."""
import pytest

from app.data.memory import InMemoryPlaceRepository
from app.data.repository import RepositoryError
from place_repo_contract import PLACES, SOURCES, PlaceRepositoryContract


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
