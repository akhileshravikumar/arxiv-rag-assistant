import pytest

from app.services.retrieval_service import RetrievalService


class FakeEmbeddingService:
    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError(
                "Search query cannot be empty."
            )

        return [0.0] * 384


def test_empty_query_is_rejected():
    service = RetrievalService(
        embedding_service=FakeEmbeddingService()
    )

    with pytest.raises(
        ValueError,
        match="Search query cannot be empty",
    ):
        service.dense_search(
            db=None,
            session_id="session-a",
            query="   ",
            top_k=5,
        )


def test_invalid_top_k_is_rejected():
    service = RetrievalService(
        embedding_service=FakeEmbeddingService()
    )

    with pytest.raises(
        ValueError,
        match="top_k must be between",
    ):
        service.dense_search(
            db=None,
            session_id="session-a",
            query="RAG",
            top_k=0,
        )
