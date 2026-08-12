from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.request_context import (
    session_id_context,
)
from app.database.database import get_db
from app.dependencies.services import Services
from app.models.session import ResearchSession
from app.services.session_service import (
    SessionNotFoundError,
)


def get_research_session(
    session_id: Annotated[
        str,
        Path(
            min_length=8,
            max_length=64,
        ),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
    services: Services,
) -> ResearchSession:
    """
    Resolve and refresh the research session named in the path.
    """
    try:
        session = services.session_service.get(
            db=db,
            session_id=session_id,
        )

    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=str(exc),
        ) from exc

    services.session_service.touch(
        db=db,
        session=session,
    )

    session_id_context.set(session.id)

    return session


CurrentSession = Annotated[
    ResearchSession,
    Depends(get_research_session),
]
