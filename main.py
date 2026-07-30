from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import (
    Base,
    SessionLocal,
    engine,
    get_db,
)
from app.middleware.request_logging import RequestLoggingMiddleware
from app.models import Chunk, Paper, User
from app.schemas.paper import PaperCreate, PaperResponse

from app.schemas.search import (
    BM25SearchRequest,
    BM25SearchResponse,
    DenseSearchRequest,
    DenseSearchResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    RerankedSearchResponse,
    RerankedSearchRequest
)

from app.schemas.errors import (
    ErrorResponse,
)
from app.services.hybrid_retrieval_service import HybridRetrievalService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from app.services.bm25_service import BM25Service

from app.services.context_builder import ContextBuilder
from app.services.reranker_service import RerankerService
from app.services.retrieval_pipeline import RetrievalPipeline

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
)
from app.services.answer_generation_service import (
    AnswerGenerationService,
)
from app.services.chat_service import ChatService

from app.models.user import User
from app.routers.auth import router as auth_router

from app.dependencies.rate_limit import (
    RateLimitedChatUser,
)

from app.dependencies.auth import AdminUser

from app.routers.ingestion import (
    router as ingestion_router,
)

from app.services.cache_key_service import (
    CacheKeyService,
)
from app.services.cache_service import (
    CacheService,
)
from app.services.redis_service import (
    redis_service,
)

from app.core.logging_config import (
    configure_logging,
)


configure_logging()
import logging


logger = logging.getLogger(__name__)

from app.core.exception_handlers import (
    register_exception_handlers,
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        Base.metadata.create_all(bind=engine)

        with SessionLocal() as db:
            indexed_documents = (
                bm25_service.build_index(db)
            )

        logger.info(
            "Database connection successful",
            extra={
                "event": "database_connected",
            },
        )
        logger.info(
            f"BM25 index built from "
            f"{indexed_documents} chunks."
        )

    except Exception as exc:
        print(f"Application startup failed: {exc}")
        raise

    yield


app = FastAPI(
    title="ArXiv RAG Assistant API",
    description="Backend API for ingesting and querying arXiv papers.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(ingestion_router)
app.add_middleware(
    RequestLoggingMiddleware
)
register_exception_handlers(app)

cache_key_service = CacheKeyService()

cache_service = CacheService(
    redis_service=redis_service,
    key_service=cache_key_service,
)
embedding_service = EmbeddingService(
    cache_service=cache_service
)

retrieval_service = RetrievalService(
    embedding_service=embedding_service
)

bm25_service = BM25Service()

hybrid_retrieval_service = HybridRetrievalService(
    dense_service=retrieval_service,
    bm25_service=bm25_service,
)
reranker_service = RerankerService(
    model_name="BAAI/bge-reranker-large",
    max_length=512,
)

context_builder = ContextBuilder(
    max_context_characters=12_000,
    max_chunk_characters=3_000,
)

retrieval_pipeline = RetrievalPipeline(
    hybrid_service=hybrid_retrieval_service,
    reranker_service=reranker_service,
    context_builder=context_builder,
    candidate_k=20,
    final_k=5,
)

answer_generation_service = (
    AnswerGenerationService()
)

chat_service = ChatService(
    retrieval_pipeline=retrieval_pipeline,
    context_builder=context_builder,
    answer_service=answer_generation_service,
    cache_service=cache_service,
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@app.get(
    "/",
    tags=["General"],
    summary="API welcome endpoint",
)
def read_root():
    return {
        "message": "Welcome to the ArXiv RAG Assistant API"
    }


@app.get(
    "/health",
    tags=["Health"],
    summary="Check API and database health",
)
def health_check(db: DatabaseSession):
    try:
        db.execute(text("SELECT 1"))
        redis_healthy = redis_service.ping()
        return {
            "status": "healthy",
            "database": "connected",

            "status": (
            "healthy" if redis_healthy
            else "degraded"
            ),
            "redis": (
                "connected"
                if redis_healthy
                else "unavailable"
            ),
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )


@app.post(
    "/papers",
    response_model=PaperResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Papers"],
    summary="Create a paper",
)
def create_paper(
    paper_data: PaperCreate,
    db: DatabaseSession,
    admin_user: AdminUser,
):
    paper = Paper(
        title=paper_data.title,
        authors=paper_data.authors,
        published=paper_data.published,
        pdf_url=str(paper_data.pdf_url),
    )

    try:
        db.add(paper)
        db.commit()
        db.refresh(paper)

        return paper

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A paper with this PDF URL already exists",
        )

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The paper could not be saved",
        )


@app.get(
    "/papers/{paper_id}",
    response_model=PaperResponse,
    tags=["Papers"],
    summary="Get a paper by ID",
)
def get_paper(
    paper_id: int,
    db: DatabaseSession,
):
    paper = db.get(Paper, paper_id)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found",
        )

    return paper


@app.get(
    "/papers",
    response_model=list[PaperResponse],
    tags=["Papers"],
    summary="List all papers",
)
def list_papers(db: DatabaseSession):
    statement = select(Paper).order_by(Paper.id)

    papers = db.scalars(statement).all()

    return papers

@app.get(
    "/papers/{paper_id}/chunks",
    tags=["Chunks"],
    summary="List chunks for one paper",
)
def list_paper_chunks(
    paper_id: int,
    db: DatabaseSession,
):
    paper = db.get(Paper, paper_id)

    if paper is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found",
        )

    statement = (
        select(Chunk)
        .where(Chunk.paper_id == paper_id)
        .order_by(Chunk.chunk_index)
    )

    chunks = db.scalars(statement).all()

    return [
        {
            "id": chunk.id,
            "paper_id": chunk.paper_id,
            "chunk_index": chunk.chunk_index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "text": chunk.text,
        }
        for chunk in chunks
    ]

@app.post(
    "/search/dense",
    response_model=DenseSearchResponse,
    tags=["Search"],
    summary="Search chunks using dense vector retrieval",
)
def dense_search(
    request: DenseSearchRequest,
    db: DatabaseSession,
):
    try:
        results = retrieval_service.dense_search(
            db=db,
            query=request.query,
            top_k=request.top_k,
        )

        return {
            "query": request.query,
            "result_count": len(results),
            "results": results,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Dense search failed",
        )
    
@app.post(
    "/search/bm25",
    response_model=BM25SearchResponse,
    tags=["Search"],
    summary="Search chunks using BM25 keyword retrieval",
)
def bm25_search(
    request: BM25SearchRequest,
):
    try:
        results = bm25_service.search(
            query=request.query,
            top_k=request.top_k,
        )

        return {
            "query": request.query,
            "result_count": len(results),
            "results": results,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(exc),
        )
    
@app.post(
    "/search/hybrid",
    response_model=HybridSearchResponse,
    tags=["Search"],
    summary=(
        "Search chunks using dense retrieval, "
        "BM25 and Reciprocal Rank Fusion"
    ),
)
def hybrid_search(
    request: HybridSearchRequest,
    db: DatabaseSession,
):
    try:
        results = (
            hybrid_retrieval_service.hybrid_search(
                db=db,
                query=request.query,
                top_k=request.top_k,
            )
        )

        return {
            "query": request.query,
            "result_count": len(results),
            "results": results,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Hybrid search failed",
        )
    
@app.post(
    "/search/reranked",
    response_model=RerankedSearchResponse,
    tags=["Search"],
    summary="Run hybrid retrieval and cross-encoder reranking",
)
def reranked_search(
    request: RerankedSearchRequest,
    db: DatabaseSession,
):
    if request.final_k > request.candidate_k:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "final_k cannot be greater "
                "than candidate_k"
            ),
        )

    try:
        results = (
            retrieval_pipeline.retrieve_and_rerank(
                db=db,
                query=request.query,
                candidate_k=request.candidate_k,
                final_k=request.final_k,
            )
        )

        return {
            "query": request.query,
            "candidate_k": request.candidate_k,
            "result_count": len(results),
            "results": results,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=str(exc),
        )

@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary=(
        "Answer a question using retrieved "
        "research-paper evidence"
    ),
    responses={
        401: {
            "model": ErrorResponse,
            "description": (
                "Authentication required"
            ),
        },
        429: {
            "model": ErrorResponse,
            "description": (
                "Rate limit exceeded"
            ),
        },
        500: {
            "model": ErrorResponse,
            "description": (
                "Unexpected server error"
            ),
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
    current_user: RateLimitedChatUser,
):
    if request.final_k > request.candidate_k:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "final_k cannot be greater "
                "than candidate_k"
            ),
        )

    try:
        result = chat_service.answer_question(
            db=db,
            question=request.question,
            candidate_k=request.candidate_k,
            final_k=request.final_k,
        )

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

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            extra={
                "event": "chat_failed",
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Answer generation failed.",
        ) from exc
    