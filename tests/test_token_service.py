import os

import jwt
import pytest


os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-that-is-long-enough",
)

from app.services.token_service import TokenService


def test_access_token_can_be_decoded():
    service = TokenService()

    token = service.create_access_token(
        user_id=1,
        email="student@example.com",
        role="user",
    )

    payload = service.decode_access_token(
        token
    )

    assert payload["user_id"] == 1
    assert payload["sub"] == (
        "student@example.com"
    )
    assert payload["role"] == "user"


def test_invalid_token_is_rejected():
    service = TokenService()

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        service.decode_access_token(
            "not-a-real-token"
        )