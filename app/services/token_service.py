import os
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256",
)
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "30",
    )
)


class TokenService:
    def __init__(self) -> None:
        if not JWT_SECRET_KEY:
            raise RuntimeError(
                "JWT_SECRET_KEY is not configured."
            )

    def create_access_token(
        self,
        *,
        user_id: int,
        email: str,
        role: str,
    ) -> str:
        now = datetime.now(timezone.utc)

        expiration = now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

        payload = {
            "sub": email,
            "user_id": user_id,
            "role": role,
            "iat": now,
            "exp": expiration,
        }

        return jwt.encode(
            payload,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

    def decode_access_token(
        self,
        token: str,
    ) -> dict:
        try:
            return jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
            )

        except InvalidTokenError as exc:
            raise ValueError(
                "Invalid or expired access token."
            ) from exc