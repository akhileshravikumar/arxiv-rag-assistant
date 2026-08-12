from app.services.reranker_service import RerankerService


CANDIDATES = [
    {
        "chunk_id": 1,
        "text": "First",
        "rrf_score": 0.03,
    },
    {
        "chunk_id": 2,
        "text": "Second",
        "rrf_score": 0.02,
    },
    {
        "chunk_id": 3,
        "text": "Third",
        "rrf_score": 0.01,
    },
]


def build_service(
    scores: list[tuple[int, float]] | None = None,
    fail: bool = False,
) -> RerankerService:
    service = RerankerService(
        api_key="test-key"
    )

    def fake_request(query, documents, top_k):
        if fail:
            raise ValueError("upstream failure")

        return scores or []

    service._request_scores = fake_request

    return service


def test_candidates_are_sorted_by_reranker_score():
    service = build_service(
        scores=[
            (0, 0.2),
            (1, 0.9),
            (2, 0.5),
        ]
    )

    results = service.rerank(
        query="test query",
        candidates=CANDIDATES,
        top_k=2,
    )

    assert results[0]["chunk_id"] == 2
    assert results[1]["chunk_id"] == 3
    assert results[0]["reranker_rank"] == 1


def test_disabled_service_preserves_fusion_order():
    service = RerankerService(api_key="")

    assert service.enabled is False

    results = service.rerank(
        query="test query",
        candidates=CANDIDATES,
        top_k=2,
    )

    assert [
        result["chunk_id"] for result in results
    ] == [1, 2]

    assert results[0]["reranker_rank"] == 1


def test_upstream_failure_falls_back_to_fusion_order():
    service = build_service(fail=True)

    results = service.rerank(
        query="test query",
        candidates=CANDIDATES,
        top_k=3,
    )

    assert [
        result["chunk_id"] for result in results
    ] == [1, 2, 3]


def test_empty_candidates_return_empty():
    service = build_service()

    assert (
        service.rerank(
            query="test query",
            candidates=[],
            top_k=5,
        )
        == []
    )
