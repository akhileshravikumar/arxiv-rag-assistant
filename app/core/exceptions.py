from typing import Any


class ApplicationError(Exception):
    status_code = 400
    code = "application_error"
    public_message = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message or self.public_message
        )

        self.public_message = (
            message or self.public_message
        )

        self.details = details


class ResourceNotFoundError(
    ApplicationError
):
    status_code = 404
    code = "resource_not_found"
    public_message = (
        "The requested resource was not found."
    )


class ConflictError(ApplicationError):
    status_code = 409
    code = "resource_conflict"
    public_message = (
        "The resource conflicts with "
        "an existing record."
    )


class ExternalServiceError(
    ApplicationError
):
    status_code = 503
    code = "external_service_unavailable"
    public_message = (
        "A required external service "
        "is temporarily unavailable."
    )