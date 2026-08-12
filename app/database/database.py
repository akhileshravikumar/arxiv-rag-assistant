from __future__ import annotations

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)


load_dotenv()


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


def resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    # psycopg 3 is the installed driver; SQLAlchemy defaults the bare
    # postgresql:// scheme to psycopg2.
    if database_url.startswith(
        "postgresql://"
    ):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return database_url


def get_engine() -> Engine:
    """
    Create the engine on first use.

    Building it lazily keeps importing a model from requiring a live
    database driver, so unit tests can exercise the service layer
    without PostgreSQL or psycopg present.
    """
    global _engine

    if _engine is None:
        _engine = create_engine(
            resolve_database_url(),
            # Serverless Postgres suspends idle compute and drops
            # connections, so verify liveness on checkout and retire
            # connections well before the provider does.
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
        )

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )

    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency providing one session per request.
    """
    db = get_session_factory()()

    try:
        yield db

    finally:
        try:
            db.close()

        except Exception:
            # close() emits a ROLLBACK. If the server already dropped
            # the connection that raises, and the driver error would
            # replace whatever the request was actually failing on.
            # Discard the connection instead, without a round trip.
            try:
                db.invalidate()
            except Exception:
                pass
