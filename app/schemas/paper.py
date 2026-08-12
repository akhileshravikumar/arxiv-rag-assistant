from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PaperResponse(BaseModel):
    id: int
    title: str
    authors: list[str]
    published: date | None
    source: str
    arxiv_id: str | None
    pdf_url: str | None
    filename: str | None
    page_count: int | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class PaperRenameRequest(BaseModel):
    title: str

    model_config = ConfigDict(
        str_min_length=1,
        str_max_length=500,
        str_strip_whitespace=True,
    )


class ArxivCandidate(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    published: str | None
    summary: str
    abstract_url: str
    pdf_url: str | None
    already_in_session: bool = False


class ArxivSearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[ArxivCandidate]
