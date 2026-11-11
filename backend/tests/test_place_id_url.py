"""place.id survives a real URL path round trip (PR #15/#16 review, DEC-017). [가상] data only.

Same pattern as ``test_app.py``: the real app from ``create_app()`` plus a test-only route, called
through TestClient. The route has the shape of the contract's ``GET /api/places/{placeId}``; that
route itself is the API layer's job and does not exist yet, so the test-only prefix is used.
The ID is put into the URL exactly as made, without encoding, the way a client would.
"""
import string
from urllib.parse import quote

from fastapi.testclient import TestClient
import pytest

from app.data.memory import InMemoryPlaceRepository
from app.data.place_id import make_place_id, parse_place_id
from app.main import create_app
from place_repo_contract import SOURCES, place

ALLOWED_CHARS = string.ascii_letters + string.digits + "_-"
ROUND_TRIP_KEYS = (["126508", "Mock_ID-01", "a" * 64, "_", "-", "--__--"]
                   + [f"a{char}b" for char in ALLOWED_CHARS])


@pytest.fixture(scope="module")
def client():
    repo = InMemoryPlaceRepository(
        [place(key, 100 + i, "CAFE") for i, key in enumerate(ROUND_TRIP_KEYS)], SOURCES)
    app = create_app()

    @app.get("/test-only/places/{placeId}")
    def get_place(placeId: str):
        found = repo.get_place(placeId)
        return {"placeId": placeId, "foundId": None if found is None else found.id}

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_tourapi_style_id_round_trips(client):
    place_id = make_place_id("tourapi-kor", "126508")
    assert place_id == "tourapi-kor:126508"
    response = client.get(f"/test-only/places/{place_id}")
    assert response.status_code == 200
    assert response.json()["placeId"] == "tourapi-kor:126508"


@pytest.mark.parametrize("key", ROUND_TRIP_KEYS)
def test_every_allowed_id_comes_back_unchanged_and_found(client, key):
    place_id = make_place_id("mock-base", key)
    assert quote(place_id, safe=":") == place_id  # nothing a client would need to encode
    response = client.get(f"/test-only/places/{place_id}")
    assert response.status_code == 200
    assert response.json() == {"placeId": place_id, "foundId": place_id}
    assert parse_place_id(response.json()["placeId"]) == ("mock-base", key)


@pytest.mark.parametrize("raw", ["mock?part", "mock#part", "mock%2Fpart", "mock%61", "mock/part",
                                 "mock part", "mock.part", "장소", "", "a" * 65])
def test_ids_that_would_break_in_a_url_cannot_be_made(raw):
    # The cases from the review (cut at ? or #, %2F → 404, %61 → "a") can no longer be produced.
    with pytest.raises(ValueError):
        make_place_id("tourapi-kor", raw)


@pytest.mark.parametrize("char", sorted(set(string.printable) - set(ALLOWED_CHARS)))
def test_every_other_printable_char_is_rejected(char):
    with pytest.raises(ValueError):
        make_place_id("tourapi-kor", f"a{char}b")
