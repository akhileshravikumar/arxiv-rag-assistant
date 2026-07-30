from app.services.rate_limit_service import (
    RateLimitService,
)
from app.services.redis_service import (
    RateLimitResult,
)


class FakeRedisService:
    def __init__(self):
        self.last_key = None

    def check_rate_limit(
        self,
        *,
        key,
        limit,
        window_seconds,
    ):
        self.last_key = key

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit - 1,
            retry_after_seconds=(
                window_seconds
            ),
        )


def test_rate_limit_uses_hashed_identifier():
    redis_service = FakeRedisService()

    service = RateLimitService(
        redis_service=redis_service
    )

    result = service.check(
        scope="chat",
        identifier="user:123",
        limit=10,
        window_seconds=60,
    )

    assert result.allowed is True
    assert "user:123" not in (
        redis_service.last_key
    )
    assert (
        "arxiv-rag:rate-limit:chat:"
        in redis_service.last_key
    )


def test_identifier_hash_is_stable():
    first = (
        RateLimitService.hash_identifier(
            "user:123"
        )
    )

    second = (
        RateLimitService.hash_identifier(
            "user:123"
        )
    )

    assert first == second