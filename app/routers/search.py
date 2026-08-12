from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.dependencies.services import Services
from app.dependencies.session import CurrentSession
from app.schemas.search import (
    BM25SearchRequest,
    BM25SearchResponse,
    DenseSearchRequest,
    DenseSearchResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    RerankedSearchRequest,
    RerankedSearchResponse,
)


# These endpoints expose each retrieval stage on its own. They are not
# used by the frontend; they exist to inspect and compare dense, lexical,
# fused and reranked results for a session.
router = APIRouter(
    prefix="/sessions/{session_id}/search",
    tags=["Search"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/dense",
    response_model=DenseSearchResponse,
    summary="Dense vector retrieval only",
)
def dense_search(
    request: DenseSearchRequest,
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
):
    try:
        results = (
            services.retrieval_service.dense_search(
                db=db,
                session_id=session.id,
                query=request.query,
                top_k=request.top_k,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    return {
        "query": request.query,
        "result_count": len(results),
        "results": results,
    }


@router.post(
    "/bm25",
    response_model=BM25SearchResponse,
    summary="BM25 keyword retrieval only",
)
def bm25_search(
    request: BM25SearchRequest,
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
):
    try:
        results = services.bm25_service.search(
            db=db,
            session_id=session.id,
            query=request.query,
            top_k=request.top_k,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    return {
        "query": request.query,
        "result_count": len(results),
        "results": results,
    }


@router.post(
    "/hybrid",
    response_model=HybridSearchResponse,
    summary=(
        "Dense and BM25 fused with Reciprocal Rank Fusion"
    ),
)
def hybrid_search(
    request: HybridSearchRequest,
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
):
    try:
        results = (
            services.hybrid_retrieval_service.hybrid_search(
                db=db,
                session_id=session.id,
                query=request.query,
                top_k=request.top_k,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    return {
        "query": request.query,
        "result_count": len(results),
        "results": results,
    }


@router.post(
    "/reranked",
    response_model=RerankedSearchResponse,
    summary="Hybrid retrieval plus reranking",
)
def reranked_search(
    request: RerankedSearchRequest,
    db: DatabaseSession,
    services: Services,
    session: CurrentSession,
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
        results = (
            services.retrieval_pipeline.retrieve_and_rerank(
                db=db,
                session_id=session.id,
                query=request.query,
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

    return {
        "query": request.query,
        "candidate_k": request.candidate_k,
        "result_count": len(results),
        "results": results,
    }
