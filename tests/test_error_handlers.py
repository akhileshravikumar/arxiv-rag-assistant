import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exception_handlers import (
    register_exception_handlers,
)
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
)
from app.middleware.request_logging import (
    RequestLoggingMiddleware,
)


class SamplePayload(BaseModel):
    count: int


def build_app() -> FastAPI:
    """
    A miniature app carrying the same middleware and handlers as the
    real one, so error shapes can be tested without a database.
    """
    app = FastAPI()

    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    @app.post("/echo")
    def echo(payload: SamplePayload):
        return {"count": payload.count}

    @app.get("/missing")
    def missing():
        raise ResourceNotFoundError(
            "Paper not found."
        )

    @app.get("/conflict")
    def conflict():
        raise ConflictError()

    @app.get("/forbidden")
    def forbidden():
        raise HTTPException(
            status_code=403,
            detail="Nope.",
        )

    return app


@pytest.fixture(name="client")
def client_fixture() -> TestClient:
    return TestClient(
        build_app(),
        raise_server_exceptions=False,
    )


def test_validation_error_format(client):
    response = client.post(
        "/echo",
        json={"count": "not-a-number"},
    )

    assert response.status_code == 422

    body = response.json()

    assert (
        body["error"]["code"]
        == "validation_error"
    )
    assert "request_id" in body["error"]


def test_application_error_uses_its_own_code(client):
    response = client.get("/missing")

    assert response.status_code == 404

    body = response.json()

    assert (
        body["error"]["code"]
        == "resource_not_found"
    )
    assert (
        body["error"]["message"]
        == "Paper not found."
    )


def test_conflict_error_uses_default_message(client):
    response = client.get("/conflict")

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == "resource_conflict"
    )


def test_http_exception_is_mapped_to_a_code(client):
    response = client.get("/forbidden")

    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "permission_denied"
    )


def test_request_id_is_returned_in_headers(client):
    response = client.get("/missing")

    assert response.headers["X-Request-ID"]
