import pytest

from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)


class FakeDenseService:
    def dense_search(
        self,
        db,
        session_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        return [
            {
                "chunk_id": 1,
                "paper_id": 1,
                "paper_title": "Paper A",
                "chunk_index": 0,
                "text": "Semantic result",
                "similarity": 0.9,
            },
            {
                "chunk_id": 2,
                "paper_id": 1,
                "paper_title": "Paper A",
                "chunk_index": 1,
                "text": "Dense-only result",
                "similarity": 0.8,
            },
        ]


class FakeBM25Service:
    def search(
        self,
        db,
        session_id: str,
        query: str,
        top_k: int,
    ) -> list[dict]:
        return [
            {
                "chunk_id": 1,
                "paper_id": 1,
                "paper_title": "Paper A",
                "chunk_index": 0,
                "text": "Semantic result",
                "score": 8.0,
                "exact_phrase_match": True,
            },
            {
                "chunk_id": 3,
                "paper_id": 2,
                "paper_title": "Paper B",
                "chunk_index": 0,
                "text": "BM25-only result",
                "score": 6.0,
                "exact_phrase_match": False,
            },
        ]


def create_service() -> HybridRetrievalService:
    return HybridRetrievalService(
        dense_service=FakeDenseService(),
        bm25_service=FakeBM25Service(),
        rrf_k=60,
    )


def test_duplicate_chunk_is_merged():
    service = create_service()

    results = service.hybrid_search(
        db=None,
        session_id="session-a",
        query="retrieval",
        top_k=3,
    )

    chunk_ids = [
        result["chunk_id"]
        for result in results
    ]

    assert chunk_ids.count(1) == 1
    assert len(chunk_ids) == len(set(chunk_ids))


def test_chunk_in_both_rankings_is_first():
    service = create_service()

    results = service.hybrid_search(
        db=None,
        session_id="session-a",
        query="retrieval",
        top_k=3,
    )

    assert results[0]["chunk_id"] == 1
    assert results[0]["retrieval_sources"] == [
        "dense",
        "bm25",
    ]


def test_empty_query_is_rejected():
    service = create_service()

    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        service.hybrid_search(
            db=None,
            session_id="session-a",
            query="   ",
            top_k=5,
        )


def test_invalid_top_k_is_rejected():
    service = create_service()

    with pytest.raises(
        ValueError,
        match="top_k must be between",
    ):
        service.hybrid_search(
            db=None,
            session_id="session-a",
            query="RAG",
            top_k=0,
        )