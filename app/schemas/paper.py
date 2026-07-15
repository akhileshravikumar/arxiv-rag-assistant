from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class PaperCreate(BaseModel):
    title: str
    authors: list[str]
    published: date
    pdf_url: HttpUrl


class PaperResponse(BaseModel):
    id: int
    title: str
    authors: list[str]
    published: date
    pdf_url: HttpUrl
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)