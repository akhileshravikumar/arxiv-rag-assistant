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
from app.models import Chunk, Paper
from app.schemas.paper import PaperCreate, PaperResponse

from app.schemas.search import (
    BM25SearchRequest,
    BM25SearchResponse,
    DenseSearchRequest,
    DenseSearchResponse,
)
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from app.services.bm25_service import BM25Service


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

        print("Database connection successful.")
        print(
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

embedding_service = EmbeddingService()
bm25_service = BM25Service()
retrieval_service = RetrievalService(
    embedding_service=embedding_service
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

        return {
            "status": "healthy",
            "database": "connected",
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