from pydantic import BaseModel, Field


class DenseSearchResult(BaseModel):
    chunk_id: int
    paper_id: int
    paper_title: str
    chunk_index: int
    text: str
    similarity: float


class DenseSearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[DenseSearchResult]


class DenseSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=1000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )