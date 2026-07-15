from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import Base, engine, get_db
from app.models.paper import Paper
from app.schemas.paper import PaperCreate, PaperResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Run application startup checks and create tables.

    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        Base.metadata.create_all(bind=engine)

        print("Database connection successful.")
        print("Database tables are ready.")

    except SQLAlchemyError as exc:
        print(f"Database startup failed: {exc}")
        raise

    yield


app = FastAPI(
    title="ArXiv RAG Assistant API",
    description="Backend API for ingesting and querying arXiv papers.",
    version="0.1.0",
    lifespan=lifespan,
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