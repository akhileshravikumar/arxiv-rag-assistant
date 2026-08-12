from collections import OrderedDict
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import Paper
from app.services.text_processing import (
    normalize_text,
    tokenize_text,
)


@dataclass(frozen=True)
class BM25Document:
    chunk_id: int
    paper_id: int
    paper_title: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class SessionIndex:
    documents: list[BM25Document]
    index: BM25Okapi


class BM25Service:
    """
    Lexical retrieval scoped to one research session.

    A session holds at most five papers (~250 chunks), so building an
    index on demand costs single-digit milliseconds. Indexes are cached
    per session and evicted least-recently-used, which keeps memory flat
    no matter how many sessions the deployment has served.
    """

    def __init__(
        self,
        phrase_boost: float = 1.5,
        max_cached_sessions: int = 20,
    ) -> None:
        if max_cached_sessions < 1:
            raise ValueError(
                "max_cached_sessions must be at least 1."
            )

        self.phrase_boost = phrase_boost
        self.max_cached_sessions = (
            max_cached_sessions
        )

        self._cache: OrderedDict[
            str,
            SessionIndex,
        ] = OrderedDict()

    def _build_for_session(
        self,
        db: Session,
        session_id: str,
    ) -> SessionIndex | None:
        statement = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.paper_id,
                Paper.title.label(
                    "paper_title"
                ),
                Chunk.chunk_index,
                Chunk.text,
            )
            .join(
                Paper,
                Paper.id == Chunk.paper_id,
            )
            .where(
                Paper.session_id == session_id
            )
            .order_by(Chunk.id)
        )

        rows = db.execute(statement).all()

        documents: list[BM25Document] = []
        tokenized_corpus: list[list[str]] = []

        for row in rows:
            tokens = tokenize_text(row.text)

            # Empty chunks carry no lexical signal.
            if not tokens:
                continue

            documents.append(
                BM25Document(
                    chunk_id=row.chunk_id,
                    paper_id=row.paper_id,
                    paper_title=row.paper_title,
                    chunk_index=row.chunk_index,
                    text=row.text,
                )
            )

            tokenized_corpus.append(tokens)

        if not documents:
            return None

        return SessionIndex(
            documents=documents,
            index=BM25Okapi(tokenized_corpus),
        )

    def get_index(
        self,
        db: Session,
        session_id: str,
    ) -> SessionIndex | None:
        if session_id in self._cache:
            self._cache.move_to_end(session_id)

            return self._cache[session_id]

        session_index = self._build_for_session(
            db=db,
            session_id=session_id,
        )

        if session_index is None:
            return None

        self._cache[session_id] = session_index

        while (
            len(self._cache)
            > self.max_cached_sessions
        ):
            self._cache.popitem(last=False)

        return session_index

    def invalidate(
        self,
        session_id: str,
    ) -> None:
        """
        Drop a cached index after the session's corpus changes.
        """
        self._cache.pop(session_id, None)

    def search(
        self,
        db: Session,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Search one session's chunks.

        An empty session returns no results rather than raising, so the
        frontend can query before any paper has been ingested.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError(
                "Search query cannot be empty."
            )

        if top_k < 1 or top_k > 100:
            raise ValueError(
                "top_k must be between 1 and 100."
            )

        session_index = self.get_index(
            db=db,
            session_id=session_id,
        )

        if session_index is None:
            return []

        query_tokens = tokenize_text(
            cleaned_query
        )

        if not query_tokens:
            return []

        bm25_scores = (
            session_index.index.get_scores(
                query_tokens
            )
        )

        normalized_query = normalize_text(
            cleaned_query
        )

        ranked_results: list[dict] = []

        for document, raw_score in zip(
            session_index.documents,
            bm25_scores,
            strict=True,
        ):
            score = float(raw_score)

            exact_phrase_match = (
                normalized_query
                in normalize_text(document.text)
            )

            if exact_phrase_match:
                score += self.phrase_boost

            # Skip chunks with no lexical overlap at all.
            if score <= 0:
                continue

            ranked_results.append(
                {
                    "chunk_id": document.chunk_id,
                    "paper_id": document.paper_id,
                    "paper_title": (
                        document.paper_title
                    ),
                    "chunk_index": (
                        document.chunk_index
                    ),
                    "text": document.text,
                    "score": round(score, 6),
                    "exact_phrase_match": (
                        exact_phrase_match
                    ),
                }
            )

        ranked_results.sort(
            key=lambda result: result["score"],
            reverse=True,
        )

        return ranked_results[:top_k]
