import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import Paper
from app.models.session import ResearchSession


load_dotenv()


SESSION_TTL_SECONDS = int(
    os.getenv(
        "SESSION_TTL_SECONDS",
        "7200",
    )
)

MAX_PAPERS_PER_SESSION = int(
    os.getenv(
        "MAX_PAPERS_PER_SESSION",
        "5",
    )
)


class SessionNotFoundError(Exception):
    """Raised when a session is unknown or has expired."""


class SessionService:
    def __init__(
        self,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        max_papers: int = MAX_PAPERS_PER_SESSION,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_papers = max_papers

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _expiry(self) -> datetime:
        return self._now() + timedelta(
            seconds=self.ttl_seconds
        )

    def purge_expired(
        self,
        db: Session,
    ) -> int:
        """
        Delete sessions past their expiry.

        Free tiers have no scheduler, so this runs opportunistically
        whenever a session is created or the health endpoint is hit.
        Papers and chunks are removed by cascade.
        """
        result = db.execute(
            delete(ResearchSession).where(
                ResearchSession.expires_at
                < self._now()
            )
        )

        db.commit()

        return result.rowcount or 0

    def create(
        self,
        db: Session,
    ) -> ResearchSession:
        self.purge_expired(db)

        now = self._now()

        # Timestamps are set here rather than left to the column's
        # server default so the object is complete after commit and
        # needs no refresh. See touch() for why that matters.
        session = ResearchSession(
            id=uuid.uuid4().hex,
            created_at=now,
            last_seen_at=now,
            expires_at=self._expiry(),
        )

        db.add(session)
        db.commit()

        return session

    def get(
        self,
        db: Session,
        session_id: str,
    ) -> ResearchSession:
        session = db.get(
            ResearchSession,
            session_id,
        )

        if session is None:
            raise SessionNotFoundError(
                "This research session no longer exists."
            )

        if session.expires_at < self._now():
            db.delete(session)
            db.commit()

            raise SessionNotFoundError(
                "This research session has expired."
            )

        return session

    def touch(
        self,
        db: Session,
        session: ResearchSession,
    ) -> ResearchSession:
        """
        Extend a session's life on activity.

        Deliberately no refresh() after commit. The session factory sets
        expire_on_commit=False, so attributes stay loaded, and refresh()
        would open a fresh transaction that stays checked out for the
        rest of the request -- including across slow external calls,
        where a serverless database will drop it underneath us.
        """
        session.last_seen_at = self._now()
        session.expires_at = self._expiry()

        db.commit()

        return session

    def delete(
        self,
        db: Session,
        session_id: str,
    ) -> bool:
        session = db.get(
            ResearchSession,
            session_id,
        )

        if session is None:
            return False

        db.delete(session)
        db.commit()

        return True

    @staticmethod
    def paper_count(
        db: Session,
        session_id: str,
    ) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Paper)
                .where(
                    Paper.session_id
                    == session_id
                )
            )
            or 0
        )

    @staticmethod
    def chunk_count(
        db: Session,
        session_id: str,
    ) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Chunk)
                .join(
                    Paper,
                    Paper.id == Chunk.paper_id,
                )
                .where(
                    Paper.session_id
                    == session_id
                )
            )
            or 0
        )

    def remaining_paper_slots(
        self,
        db: Session,
        session_id: str,
    ) -> int:
        return max(
            self.max_papers
            - self.paper_count(
                db,
                session_id,
            ),
            0,
        )
