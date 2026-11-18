"""Common HTTP boundary tests; no LLM or DB calls."""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()

    class Input(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        count: int

    @app.post("/test-only/input")
    def validate(body: Input):
        return {"count": body.count}

    @app.get("/test-only/crash")
    def crash():
        raise RuntimeError("private-sentinel")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def check_error(response, status, code):
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"error", "requestId"}
    UUID(body["requestId"])
    assert body["error"]["code"] == code
    assert body["error"]["details"] == []
    assert "private-sentinel" not in response.text


def test_only_implemented_routes_are_documented():
    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 200
        assert set(client.get("/openapi.json").json()["paths"]) == {'/api/sessions', '/api/sessions/{sessionId}', '/api/sessions/{sessionId}/profile'}


def test_missing_route_and_unique_request_id(client):
    first = client.get("/api/private-sentinel")
    second = client.get("/api/private-sentinel")
    check_error(first, 404, "NOT_FOUND")
    assert first.json()["requestId"] != second.json()["requestId"]


@pytest.mark.parametrize("body", [{"count": "private-sentinel"}, {"count": 1, "extra": "private-sentinel"}])
def test_validation_does_not_echo_input(client, body):
    check_error(client.post("/test-only/input", json=body), 422, "INVALID_REQUEST")


def test_malformed_json(client):
    check_error(client.post("/test-only/input", content='{"private-sentinel":', headers={"Content-Type": "application/json"}), 400, "INVALID_REQUEST")


def test_unexpected_exception_is_sanitized(client):
    check_error(client.get("/test-only/crash"), 500, "INTERNAL_ERROR")
