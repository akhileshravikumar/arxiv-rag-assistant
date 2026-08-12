import logging

from fastapi import (
    HTTPException,
    Request,
    Response,
    status,
)

from app.dependencies.session import CurrentSession
from app.models.session import ResearchSession
from app.services.rate_limit_service import (
    CHAT_RATE_LIMIT_REQUESTS,
    CHAT_RATE_LIMIT_WINDOW_SECONDS,
    INGESTION_RATE_LIMIT_REQUESTS,
    INGESTION_RATE_LIMIT_WINDOW_SECONDS,
    SESSION_CREATE_RATE_LIMIT_REQUESTS,
    SESSION_CREATE_RATE_LIMIT_WINDOW_SECONDS,
    RateLimitService,
)
from app.services.redis_service import (
    redis_service,
)


logger = logging.getLogger(__name__)


rate_limit_service = RateLimitService(
    redis_service=redis_service
)


def client_identifier(
    request: Request,
) -> str:
    """
    Best-effort client address behind a platform proxy.
    """
    forwarded_for = request.headers.get(
        "X-Forwarded-For"
    )

    if forwarded_for:
        return forwarded_for.split(",")[
            0
        ].strip()

    return (
        request.client.host
        if request.client
        else "unknown"
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
        # Fail open so a Redis outage does not disable the API.
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


def limit_session_creation(
    request: Request,
    response: Response,
) -> None:
    enforce_rate_limit(
        request=request,
        response=response,
        identifier=(
            f"ip:{client_identifier(request)}"
        ),
        scope="session-create",
        limit=(
            SESSION_CREATE_RATE_LIMIT_REQUESTS
        ),
        window_seconds=(
            SESSION_CREATE_RATE_LIMIT_WINDOW_SECONDS
        ),
    )


def limit_chat_requests(
    request: Request,
    response: Response,
    session: CurrentSession,
) -> ResearchSession:
    enforce_rate_limit(
        request=request,
        response=response,
        identifier=f"session:{session.id}",
        scope="chat",
        limit=CHAT_RATE_LIMIT_REQUESTS,
        window_seconds=(
            CHAT_RATE_LIMIT_WINDOW_SECONDS
        ),
    )

    return session


def limit_ingestion_requests(
    request: Request,
    response: Response,
    session: CurrentSession,
) -> ResearchSession:
    enforce_rate_limit(
        request=request,
        response=response,
        identifier=f"session:{session.id}",
        scope="ingestion",
        limit=INGESTION_RATE_LIMIT_REQUESTS,
        window_seconds=(
            INGESTION_RATE_LIMIT_WINDOW_SECONDS
        ),
    )

    enforce_rate_limit(
        request=request,
        response=response,
        identifier=(
            f"ip:{client_identifier(request)}"
        ),
        scope="ingestion-ip",
        limit=INGESTION_RATE_LIMIT_REQUESTS * 3,
        window_seconds=(
            INGESTION_RATE_LIMIT_WINDOW_SECONDS
        ),
    )

    return session
