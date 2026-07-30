from fastapi.testclient import (
    TestClient,
)

from main import app


client = TestClient(
    app,
    raise_server_exceptions=False,
)


def test_validation_error_format():
    response = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "short",
        },
    )

    assert response.status_code == 422

    body = response.json()

    assert "error" in body
    assert (
        body["error"]["code"]
        == "validation_error"
    )
    assert "request_id" in body["error"]


def test_missing_auth_error_format():
    response = client.get(
        "/auth/me"
    )

    assert response.status_code == 401

    body = response.json()

    assert "error" in body
    assert body["error"]["code"] == (
        "authentication_required"
    )