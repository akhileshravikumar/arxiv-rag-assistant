import numpy as np

from app.services.reranker_service import RerankerService


class FakeCrossEncoder:
    def predict(
        self,
        pairs,
        batch_size,
        show_progress_bar,
    ):
        return np.array(
            [
                0.2,
                0.9,
                0.5,
            ]
        )


def test_candidates_are_sorted_by_reranker_score():
    service = RerankerService.__new__(
        RerankerService
    )
    service.model = FakeCrossEncoder()

    candidates = [
        {"chunk_id": 1, "text": "First"},
        {"chunk_id": 2, "text": "Second"},
        {"chunk_id": 3, "text": "Third"},
    ]

    results = service.rerank(
        query="test query",
        candidates=candidates,
        top_k=2,
    )

    assert results[0]["chunk_id"] == 2
    assert results[1]["chunk_id"] == 3
    assert results[0]["reranker_rank"] == 1