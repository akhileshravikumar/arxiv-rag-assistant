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

class BM25SearchResult(BaseModel):
    chunk_id: int
    paper_id: int
    paper_title: str
    chunk_index: int
    text: str
    score: float
    exact_phrase_match: bool


class BM25SearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=1000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class BM25SearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[BM25SearchResult]

class HybridSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=1000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class HybridSearchResult(BaseModel):
    chunk_id: int
    paper_id: int
    paper_title: str
    chunk_index: int
    text: str

    rrf_score: float

    dense_rank: int | None = None
    dense_similarity: float | None = None

    bm25_rank: int | None = None
    bm25_score: float | None = None
    exact_phrase_match: bool = False

    retrieval_sources: list[str]


class HybridSearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[HybridSearchResult]