import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.dependencies.rate_limit import (
    limit_chat_requests,
)
from app.dependencies.services import Services
from app.models.session import ResearchSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.errors import ErrorResponse


logger = logging.getLogger(__name__)


router = APIRouter(tags=["Chat"])


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]

RateLimitedSession = Annotated[
    ResearchSession,
    Depends(limit_chat_requests),
]


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    summary=(
        "Answer a question from the session's papers"
    ),
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "Session not found or expired"
            ),
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded",
        },
        503: {
            "model": ErrorResponse,
            "description": (
                "Required service unavailable"
            ),
        },
    },
)
def chat(
    request: ChatRequest,
    db: DatabaseSession,
    services: Services,
    session: RateLimitedSession,
):
    if request.final_k > request.candidate_k:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "final_k cannot be greater "
                "than candidate_k"
            ),
        )

    try:
        result = (
            services.chat_service.answer_question(
                db=db,
                session_id=session.id,
                question=request.question,
                candidate_k=request.candidate_k,
                final_k=request.final_k,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected chat error",
            extra={"event": "chat_failed"},
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Answer generation failed.",
        ) from exc

    session.question_count += 1
    db.commit()

    return {
        "question": result.question,
        "answer": result.answer,
        "model": result.model,
        "cited_source_numbers": (
            result.cited_source_numbers
        ),
        "sources": result.sources,
        "context_character_count": (
            result.context_character_count
        ),
        "estimated_context_tokens": (
            result.estimated_context_tokens
        ),
        "cache_hit": result.cache_hit,
    }
