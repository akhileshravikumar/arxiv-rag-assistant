import logging
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)

from app.dependencies.auth import (
    AdminUser,
    CurrentUser,
)
from app.models.user import User
from app.services.rate_limit_service import (
    CHAT_RATE_LIMIT_REQUESTS,
    CHAT_RATE_LIMIT_WINDOW_SECONDS,
    INGESTION_RATE_LIMIT_REQUESTS,
    INGESTION_RATE_LIMIT_WINDOW_SECONDS,
    RateLimitService,
)
from app.services.redis_service import (
    redis_service,
)


logger = logging.getLogger(__name__)


rate_limit_service = RateLimitService(
    redis_service=redis_service
)


def enforce_rate_limit(
    *,
    request: Request,
    response: Response,
    identifier: str,
    scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    try:
        result = rate_limit_service.check(
            scope=scope,
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )

    except RuntimeError:
        # Fail open for now so a Redis outage does not
        # completely disable the API.
        logger.warning(
            "Rate limiter unavailable",
            extra={
                "event": (
                    "rate_limiter_unavailable"
                ),
                "scope": scope,
                "path": request.url.path,
            },
        )

        return

    response.headers[
        "X-RateLimit-Limit"
    ] = str(result.limit)

    response.headers[
        "X-RateLimit-Remaining"
    ] = str(result.remaining)

    if not result.allowed:
        logger.warning(
            "Rate limit exceeded",
            extra={
                "event": "rate_limit_exceeded",
                "scope": scope,
                "path": request.url.path,
                "retry_after_seconds": (
                    result.retry_after_seconds
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Rate limit exceeded. "
                "Please retry later."
            ),
            headers={
                "Retry-After": str(
                    result.retry_after_seconds
                ),
                "X-RateLimit-Limit": str(
                    result.limit
                ),
                "X-RateLimit-Remaining": "0",
            },
        )


def limit_chat_requests(
    request: Request,
    response: Response,
    current_user: CurrentUser,
) -> User:
    enforce_rate_limit(
        request=request,
        response=response,
        identifier=f"user:{current_user.id}",
        scope="chat",
        limit=CHAT_RATE_LIMIT_REQUESTS,
        window_seconds=(
            CHAT_RATE_LIMIT_WINDOW_SECONDS
        ),
    )

    return current_user


def limit_ingestion_requests(
    request: Request,
    response: Response,
    admin_user: AdminUser,
) -> User:
    enforce_rate_limit(
        request=request,
        response=response,
        identifier=f"user:{admin_user.id}",
        scope="ingestion",
        limit=(
            INGESTION_RATE_LIMIT_REQUESTS
        ),
        window_seconds=(
            INGESTION_RATE_LIMIT_WINDOW_SECONDS
        ),
    )

    return admin_user


RateLimitedChatUser = Annotated[
    User,
    Depends(limit_chat_requests),
]


RateLimitedAdminUser = Annotated[
    User,
    Depends(limit_ingestion_requests),
]