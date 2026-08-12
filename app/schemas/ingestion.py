from pydantic import BaseModel, Field


class ArxivIngestionRequest(BaseModel):
    arxiv_ids: list[str] = Field(
        min_length=1,
        max_length=5,
        examples=[["2005.11401", "1706.03762"]],
    )


class JobSubmissionResponse(BaseModel):
    job_id: str
    state: str
    status_url: str
    message: str


class JobPaperStatus(BaseModel):
    label: str
    stage: str
    progress: int
    paper_id: int | None = None
    title: str | None = None
    error: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    session_id: str
    state: str
    overall_progress: int
    created_at: str
    updated_at: str
    error: str | None = None
    papers: list[JobPaperStatus]
