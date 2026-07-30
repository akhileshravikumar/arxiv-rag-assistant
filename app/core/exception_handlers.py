import logging
from typing import Any

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import JSONResponse
from starlette import status

from app.core.exceptions import (
    ApplicationError,
)


logger = logging.getLogger(__name__)


def get_request_id(
    request: Request,
) -> str | None:
    return getattr(
        request.state,
        "request_id",
        None,
    )


def create_error_payload(
    *,
    request: Request,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(
                request
            ),
            "details": details,
        }
    }


def register_exception_handlers(
    app: FastAPI,
) -> None:
    @app.exception_handler(
        ApplicationError
    )
    async def handle_application_error(
        request: Request,
        exc: ApplicationError,
    ):
        logger.warning(
            "Application error",
            extra={
                "event": "application_error",
                "error_code": exc.code,
                "status_code": (
                    exc.status_code
                ),
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_payload(
                request=request,
                code=exc.code,
                message=exc.public_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request,
        exc: HTTPException,
    ):
        code_by_status = {
            400: "bad_request",
            401: "authentication_required",
            403: "permission_denied",
            404: "resource_not_found",
            409: "resource_conflict",
            422: "validation_error",
            429: "rate_limit_exceeded",
            503: "service_unavailable",
        }

        code = code_by_status.get(
            exc.status_code,
            "http_error",
        )

        response = JSONResponse(
            status_code=exc.status_code,
            content=create_error_payload(
                request=request,
                code=code,
                message=str(exc.detail),
            ),
            headers=exc.headers,
        )

        return response

    @app.exception_handler(
        RequestValidationError
    )
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ):
        safe_details = []

        for error in exc.errors():
            safe_details.append(
                {
                    "location": list(
                        error.get("loc", [])
                    ),
                    "message": error.get(
                        "msg"
                    ),
                    "type": error.get(
                        "type"
                    ),
                }
            )

        return JSONResponse(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            content=create_error_payload(
                request=request,
                code="validation_error",
                message=(
                    "The request contains "
                    "invalid data."
                ),
                details=safe_details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ):
        logger.exception(
            "Unhandled application error",
            extra={
                "event": "unhandled_exception",
                "path": request.url.path,
                "exception_type": (
                    type(exc).__name__
                ),
            },
        )

        return JSONResponse(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            content=create_error_payload(
                request=request,
                code="internal_server_error",
                message=(
                    "An unexpected error occurred."
                ),
            ),
        )