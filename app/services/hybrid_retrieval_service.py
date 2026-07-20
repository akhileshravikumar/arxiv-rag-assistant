from sqlalchemy.orm import Session

from app.services.bm25_service import BM25Service
from app.services.retrieval_service import RetrievalService


class HybridRetrievalService:
    def __init__(
        self,
        dense_service: RetrievalService,
        bm25_service: BM25Service,
        rrf_k: int = 60,
        candidate_multiplier: int = 4,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be greater than zero.")

        if candidate_multiplier < 1:
            raise ValueError(
                "candidate_multiplier must be greater than zero."
            )

        self.dense_service = dense_service
        self.bm25_service = bm25_service
        self.rrf_k = rrf_k
        self.candidate_multiplier = candidate_multiplier

    def _rrf_score(
        self,
        rank: int,
    ) -> float:
        """
        Calculate the Reciprocal Rank Fusion contribution
        for one result position.

        Rank starts at 1.
        """
        return 1.0 / (self.rrf_k + rank)

    def hybrid_search(
        self,
        db: Session,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Run dense and BM25 retrieval, merge duplicate chunks,
        and rank them using Reciprocal Rank Fusion.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Search query cannot be empty.")

        if top_k < 1 or top_k > 20:
            raise ValueError(
                "top_k must be between 1 and 20."
            )

        candidate_count = min(
            top_k * self.candidate_multiplier,
            100,
        )

        dense_results = self.dense_service.dense_search(
            db=db,
            query=cleaned_query,
            top_k=candidate_count,
        )

        bm25_results = self.bm25_service.search(
            query=cleaned_query,
            top_k=candidate_count,
        )

        fused_results: dict[int, dict] = {}

        for dense_rank, result in enumerate(
            dense_results,
            start=1,
        ):
            chunk_id = result["chunk_id"]

            fused_results[chunk_id] = {
                "chunk_id": chunk_id,
                "paper_id": result["paper_id"],
                "paper_title": result["paper_title"],
                "chunk_index": result["chunk_index"],
                "text": result["text"],
                "rrf_score": self._rrf_score(
                    dense_rank
                ),
                "dense_rank": dense_rank,
                "dense_similarity": result["similarity"],
                "bm25_rank": None,
                "bm25_score": None,
                "exact_phrase_match": False,
                "retrieval_sources": ["dense"],
            }

        for bm25_rank, result in enumerate(
            bm25_results,
            start=1,
        ):
            chunk_id = result["chunk_id"]

            rrf_contribution = self._rrf_score(
                bm25_rank
            )

            if chunk_id in fused_results:
                fused_result = fused_results[chunk_id]

                fused_result["rrf_score"] += (
                    rrf_contribution
                )
                fused_result["bm25_rank"] = bm25_rank
                fused_result["bm25_score"] = result["score"]
                fused_result["exact_phrase_match"] = (
                    result["exact_phrase_match"]
                )
                fused_result["retrieval_sources"].append(
                    "bm25"
                )

            else:
                fused_results[chunk_id] = {
                    "chunk_id": chunk_id,
                    "paper_id": result["paper_id"],
                    "paper_title": result["paper_title"],
                    "chunk_index": result["chunk_index"],
                    "text": result["text"],
                    "rrf_score": rrf_contribution,
                    "dense_rank": None,
                    "dense_similarity": None,
                    "bm25_rank": bm25_rank,
                    "bm25_score": result["score"],
                    "exact_phrase_match": (
                        result["exact_phrase_match"]
                    ),
                    "retrieval_sources": ["bm25"],
                }

        ranked_results = sorted(
            fused_results.values(),
            key=lambda result: (
                result["rrf_score"],
                result["dense_similarity"]
                if result["dense_similarity"] is not None
                else float("-inf"),
            ),
            reverse=True,
        )

        for result in ranked_results:
            result["rrf_score"] = round(
                result["rrf_score"],
                8,
            )

        return ranked_results[:top_k]