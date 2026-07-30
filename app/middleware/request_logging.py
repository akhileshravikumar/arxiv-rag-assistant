import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import (
    BaseHTTPMiddleware,
)
from starlette.responses import Response

from app.core.request_context import (
    request_id_context,
)


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(
    BaseHTTPMiddleware
):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        supplied_request_id = (
            request.headers.get(
                "X-Request-ID"
            )
        )

        request_id = (
            supplied_request_id.strip()
            if supplied_request_id
            else str(uuid.uuid4())
        )

        request.state.request_id = request_id

        context_token = (
            request_id_context.set(
                request_id
            )
        )

        started_at = time.perf_counter()

        logger.info(
            "Request started",
            extra={
                "event": "request_started",
                "method": request.method,
                "path": request.url.path,
                "client_ip": (
                    request.client.host
                    if request.client
                    else None
                ),
            },
        )

        try:
            response = await call_next(
                request
            )

        except Exception:
            duration_ms = (
                time.perf_counter()
                - started_at
            ) * 1000

            logger.exception(
                "Request failed",
                extra={
                    "event": "request_failed",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(
                        duration_ms,
                        2,
                    ),
                },
            )

            raise

        else:
            duration_ms = (
                time.perf_counter()
                - started_at
            ) * 1000

            response.headers[
                "X-Request-ID"
            ] = request_id

            response.headers[
                "X-Process-Time-Ms"
            ] = f"{duration_ms:.2f}"

            logger.info(
                "Request completed",
                extra={
                    "event": "request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": (
                        response.status_code
                    ),
                    "duration_ms": round(
                        duration_ms,
                        2,
                    ),
                },
            )

            return response

        finally:
            request_id_context.reset(
                context_token
            )