import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# Read variables from the .env file.
load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to the project's .env file."
    )


# The engine manages connections to PostgreSQL.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# SessionLocal is a factory that creates database sessions.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# All SQLAlchemy database models will inherit from this class.
class Base(DeclarativeBase):
    pass


# FastAPI dependency that provides one session per request.
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()