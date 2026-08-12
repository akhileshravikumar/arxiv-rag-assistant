from datetime import datetime

from pydantic import BaseModel

from app.schemas.paper import PaperResponse


class SessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    paper_count: int
    chunk_count: int
    max_papers: int
    remaining_paper_slots: int
    question_count: int


class SessionDetailResponse(SessionResponse):
    papers: list[PaperResponse]
