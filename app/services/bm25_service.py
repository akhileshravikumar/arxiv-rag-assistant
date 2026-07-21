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


class BM25Service:
    def __init__(
        self,
        phrase_boost: float = 1.5,
    ) -> None:
        self.phrase_boost = phrase_boost
        self.documents: list[BM25Document] = []
        self.tokenized_corpus: list[list[str]] = []
        self.index: BM25Okapi | None = None

    def build_index(
        self,
        db: Session,
    ) -> int:
        """
        Load all chunk text from PostgreSQL and build
        an in-memory BM25 index.
        """
        statement = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.paper_id,
                Paper.title.label("paper_title"),
                Chunk.chunk_index,
                Chunk.text,
            )
            .join(
                Paper,
                Paper.id == Chunk.paper_id,
            )
            .order_by(Chunk.id)
        )

        rows = db.execute(statement).all()

        if not rows:
            raise RuntimeError(
                "No chunks exist. Run the ingestion pipeline first."
            )

        documents: list[BM25Document] = []
        tokenized_corpus: list[list[str]] = []

        for row in rows:
            tokens = tokenize_text(row.text)

            # Empty chunks provide no searchable lexical content.
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
            raise RuntimeError(
                "No searchable chunk text was found."
            )

        self.documents = documents
        self.tokenized_corpus = tokenized_corpus
        self.index = BM25Okapi(tokenized_corpus)

        return len(documents)

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Search the in-memory BM25 index.

        An additional phrase boost is applied when the complete
        normalized query appears in the chunk.
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

        if self.index is None:
            raise RuntimeError(
                "BM25 index has not been built."
            )

        query_tokens = tokenize_text(cleaned_query)

        if not query_tokens:
            raise ValueError(
                "Search query contains no searchable terms."
            )

        bm25_scores = self.index.get_scores(
            query_tokens
        )

        normalized_query = normalize_text(
            cleaned_query
        )

        ranked_results: list[dict] = []

        for document, raw_score in zip(
            self.documents,
            bm25_scores,
            strict=True,
        ):
            score = float(raw_score)

            normalized_document = normalize_text(
                document.text
            )

            exact_phrase_match = (
                normalized_query in normalized_document
            )

            if exact_phrase_match:
                score += self.phrase_boost

            # Avoid returning chunks with no lexical match.
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