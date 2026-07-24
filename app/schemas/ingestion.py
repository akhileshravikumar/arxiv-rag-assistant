from typing import Any

from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    arxiv_id: str = Field(
        min_length=3,
        max_length=100,
        examples=["2005.11401"],
    )


class IngestionSubmissionResponse(BaseModel):
    task_id: str
    status: str
    status_url: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    ready: bool
    successful: bool | None
    progress: int | None = None
    stage: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None