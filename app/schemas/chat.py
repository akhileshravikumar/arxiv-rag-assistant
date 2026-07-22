from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
    )

    candidate_k: int = Field(
        default=20,
        ge=1,
        le=50,
    )

    final_k: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class ChatSource(BaseModel):
    source_number: int
    paper_id: int
    paper_title: str
    chunk_id: int
    chunk_index: int
    reranker_rank: int
    reranker_score: float
    cited_in_answer: bool
    text_preview: str


class ChatResponse(BaseModel):
    question: str
    answer: str
    model: str
    cited_source_numbers: list[int]
    sources: list[ChatSource]
    context_character_count: int
    estimated_context_tokens: int