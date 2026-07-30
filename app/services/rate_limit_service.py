import hashlib
import os

from dotenv import load_dotenv

from app.services.redis_service import (
    RateLimitResult,
    RedisService,
)


load_dotenv()


class RateLimitService:
    def __init__(
        self,
        redis_service: RedisService,
    ) -> None:
        self.redis_service = redis_service

    @staticmethod
    def hash_identifier(
        identifier: str,
    ) -> str:
        return hashlib.sha256(
            identifier.encode("utf-8")
        ).hexdigest()[:24]

    def check(
        self,
        *,
        scope: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        identifier_hash = self.hash_identifier(
            identifier
        )

        key = (
            f"arxiv-rag:rate-limit:"
            f"{scope}:{identifier_hash}"
        )

        return self.redis_service.check_rate_limit(
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )


CHAT_RATE_LIMIT_REQUESTS = int(
    os.getenv(
        "CHAT_RATE_LIMIT_REQUESTS",
        "10",
    )
)

CHAT_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv(
        "CHAT_RATE_LIMIT_WINDOW_SECONDS",
        "60",
    )
)

INGESTION_RATE_LIMIT_REQUESTS = int(
    os.getenv(
        "INGESTION_RATE_LIMIT_REQUESTS",
        "5",
    )
)

INGESTION_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv(
        "INGESTION_RATE_LIMIT_WINDOW_SECONDS",
        "3600",
    )
)