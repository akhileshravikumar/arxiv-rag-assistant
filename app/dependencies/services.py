from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.container import ServiceContainer


def get_services(
    request: Request,
) -> ServiceContainer:
    services = getattr(
        request.app.state,
        "services",
        None,
    )

    if services is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The application is still starting."
            ),
        )

    return services


Services = Annotated[
    ServiceContainer,
    Depends(get_services),
]
