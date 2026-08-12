from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


PAPER_SOURCE_ARXIV = "arxiv"
PAPER_SOURCE_UPLOAD = "upload"


class Paper(Base):
    __tablename__ = "papers"

    __table_args__ = (
        # Uniqueness is per session: two people researching the same
        # topic will legitimately want the same paper.
        UniqueConstraint(
            "session_id",
            "pdf_url",
            name="uq_papers_session_pdf_url",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey(
            "research_sessions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    authors: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
    )

    published: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PAPER_SOURCE_ARXIV,
    )

    arxiv_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Uploaded papers have no canonical URL.
    pdf_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
