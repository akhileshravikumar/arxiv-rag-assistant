from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
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

    published: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    pdf_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )