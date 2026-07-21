from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import Paper
from app.services.embedding_service import EmbeddingService


class RetrievalService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        self.embedding_service = embedding_service

    def dense_search(
        self,
        db: Session,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Return chunks ordered by cosine similarity to the query.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Search query cannot be empty.")

        if top_k < 1 or top_k > 100:
            raise ValueError(
                "top_k must be between 1 and 100."
        )

        query_embedding = (
            self.embedding_service.embed_query(
                cleaned_query
            )
        )

        cosine_distance = (
            Chunk.embedding.cosine_distance(
                query_embedding
            )
        )

        statement = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.paper_id,
                Paper.title.label("paper_title"),
                Chunk.chunk_index,
                Chunk.text,
                cosine_distance.label(
                    "cosine_distance"
                ),
            )
            .join(
                Paper,
                Paper.id == Chunk.paper_id,
            )
            .where(
                Chunk.embedding.is_not(None)
            )
            .order_by(
                cosine_distance
            )
            .limit(top_k)
        )

        rows = db.execute(statement).all()

        results: list[dict] = []

        for row in rows:
            distance = float(row.cosine_distance)
            similarity = 1.0 - distance

            results.append(
                {
                    "chunk_id": row.chunk_id,
                    "paper_id": row.paper_id,
                    "paper_title": row.paper_title,
                    "chunk_index": row.chunk_index,
                    "text": row.text,
                    "similarity": round(
                        similarity,
                        6,
                    ),
                }
            )

        return results