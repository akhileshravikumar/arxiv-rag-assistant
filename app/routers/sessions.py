from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.dependencies.rate_limit import (
    limit_session_creation,
)
from app.dependencies.services import Services
from app.dependencies.session import CurrentSession
from app.models.paper import Paper
from app.schemas.paper import (
    ArxivCandidate,
    ArxivSearchResponse,
    PaperRenameRequest,
    PaperResponse,
)
from app.schemas.session import (
    SessionDetailResponse,
    SessionResponse,
)
from app.services.arxiv_service import (
    build_bibtex_entry,
    search_arxiv,
)


router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


def list_session_papers(
    db: Session,
    session_id: str,
) -> list[Paper]:
    statement = (
        select(Paper)
        .where(Paper.session_id == session_id)
        .order_by(Paper.id)
    )

    return list(db.scalars(statement).all())


def build_session_payload(
    db: Session,
    services: Services,
    session,
) -> dict:
    session_service = services.session_service

    paper_count = session_service.paper_count(
        db,
        session.id,
    )

    return {
        "session_id": session.id,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "paper_count": paper_count,
        "chunk_count": (
            session_service.chunk_count(
                db,
                session.id,
            )
        ),
        "max_papers": session_service.max_papers,
        "remaining_paper_slots": max(
            session_service.max_papers
            - paper_count,
            0,
        ),
        "question_count": session.question_count,
    }


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(limit_session_creation)
    ],
    summary="Start a research session",
)
def create_session(
    db: DatabaseSession,
    services: Services,
):
    session = services.session_service.create(db)

    return build_session_payload(
        db=db,
        services=services,
        session=session,
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get a session and its papers",
)
def get_session(
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
):
    payload = build_session_payload(
        db=db,
        services=services,
        session=session,
    )

    payload["papers"] = list_session_papers(
        db,
        session.id,
    )

    return payload


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session and everything in it",
)
def delete_session(
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
):
    services.bm25_service.invalidate(session.id)

    services.session_service.delete(
        db=db,
        session_id=session.id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.get(
    "/{session_id}/arxiv/search",
    response_model=ArxivSearchResponse,
    summary="Preview arXiv results before ingesting",
)
def search_arxiv_candidates(
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
    q: Annotated[
        str,
        Query(
            min_length=2,
            max_length=300,
        ),
    ],
    max_results: Annotated[
        int,
        Query(ge=1, le=5),
    ] = 5,
):
    """
    Metadata only. Nothing is downloaded until the user confirms.
    """
    try:
        papers = search_arxiv(
            search_term=q,
            max_results=max_results,
        )

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=str(exc),
        ) from exc

    existing_ids = {
        (paper.arxiv_id or "").split(
            "v",
            maxsplit=1,
        )[0]
        for paper in list_session_papers(
            db,
            session.id,
        )
        if paper.arxiv_id
    }

    results = [
        ArxivCandidate(
            arxiv_id=paper["arxiv_id"],
            title=paper["title"],
            authors=paper["authors"],
            published=paper["published"] or None,
            summary=paper["summary"],
            abstract_url=paper["abstract_url"],
            pdf_url=paper["pdf_url"],
            already_in_session=(
                paper["arxiv_id"].split(
                    "v",
                    maxsplit=1,
                )[0]
                in existing_ids
            ),
        )
        for paper in papers
    ]

    return {
        "query": q,
        "result_count": len(results),
        "results": results,
    }


@router.get(
    "/{session_id}/papers",
    response_model=list[PaperResponse],
    summary="List the session's papers",
)
def list_papers(
    db: DatabaseSession,
    session: CurrentSession,
):
    return list_session_papers(db, session.id)


@router.patch(
    "/{session_id}/papers/{paper_id}",
    response_model=PaperResponse,
    summary="Rename a paper",
)
def rename_paper(
    paper_id: int,
    request: PaperRenameRequest,
    db: DatabaseSession,
    session: CurrentSession,
):
    paper = db.get(Paper, paper_id)

    if (
        paper is None
        or paper.session_id != session.id
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Paper not found.",
        )

    paper.title = request.title.strip()

    db.commit()
    db.refresh(paper)

    return paper


@router.get(
    "/{session_id}/papers/bibtex",
    response_class=PlainTextResponse,
    summary="Download the session's references as BibTeX",
)
def download_bibtex(
    db: DatabaseSession,
    session: CurrentSession,
):
    papers = list_session_papers(db, session.id)

    entries = [
        build_bibtex_entry(
            {
                "title": paper.title,
                "authors": paper.authors,
                "published": paper.published,
                "arxiv_id": paper.arxiv_id,
            }
        )
        for paper in papers
    ]

    return PlainTextResponse(
        content="\n\n".join(entries) + "\n",
        headers={
            "Content-Disposition": (
                'attachment; filename="references.bib"'
            )
        },
    )
