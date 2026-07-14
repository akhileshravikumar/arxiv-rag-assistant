from fastapi import Depends, FastAPI, status
from pydantic import BaseModel

app = FastAPI()

class PaperCreate(BaseModel):
    title: str
    authors: list[str]
    abstract: str

class PaperResponse(BaseModel):
    id: int
    title: str
    authors: list[str]
    abstract: str
    status: str

class RootResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str

def get_application_name() -> str:
    return "ArXiv RAG Assistant"

app = FastAPI(
    title="ArXiv RAG Assistant API",
    description="Backend API for ingesting and querying arXiv research papers.",
    version="0.1.0"
)

@app.get(
    "/",
    response_model=RootResponse,
    tags=["General"],
    summary="API welcome endpoint"
)
def read_root(
    application_name: str = Depends(get_application_name)
):
    return {
        "message": f"Welcome to {application_name}"
    }

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Check API health"
)
def health_check():
    return {"status": "healthy"}


@app.post(
    "/papers",
    response_model=PaperResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Papers"],
    summary="Submit paper metadata"
)
def create_paper(paper: PaperCreate):
    return {
        "id": 1,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "status": "received"
    }