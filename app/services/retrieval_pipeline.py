from sqlalchemy.orm import Session

from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from app.services.reranker_service import (
    RerankerService,
)
from app.services.context_builder import (
    ContextBuildResult,
    ContextBuilder,
)


class RetrievalPipeline:
    def __init__(
        self,
        hybrid_service: HybridRetrievalService,
        reranker_service: RerankerService,
        context_builder: ContextBuilder,
        candidate_k: int = 20,
        final_k: int = 5,
    ) -> None:
        if candidate_k < final_k:
            raise ValueError(
                "candidate_k must be greater than "
                "or equal to final_k."
            )

        self.hybrid_service = hybrid_service
        self.reranker_service = reranker_service
        self.context_builder = context_builder
        self.candidate_k = candidate_k
        self.final_k = final_k

    def retrieve_and_rerank(
        self,
        db: Session,
        query: str,
        candidate_k: int | None = None,
        final_k: int | None = None,
    ) -> list[dict]:
        """
        Retrieve broadly using hybrid search, then rerank.
        """
        resolved_candidate_k = (
            candidate_k
            if candidate_k is not None
            else self.candidate_k
        )

        resolved_final_k = (
            final_k
            if final_k is not None
            else self.final_k
        )

        if resolved_candidate_k < resolved_final_k:
            raise ValueError(
                "candidate_k cannot be smaller than final_k."
            )

        candidates = self.hybrid_service.hybrid_search(
            db=db,
            query=query,
            top_k=resolved_candidate_k,
        )

        return self.reranker_service.rerank(
            query=query,
            candidates=candidates,
            top_k=resolved_final_k,
        )
    
    def retrieve_rerank_and_build_context(
        self,
        db: Session,
        query: str,
        candidate_k: int | None = None,
        final_k: int | None = None,
    ) -> ContextBuildResult:
        reranked_chunks = self.retrieve_and_rerank(
            db=db,
            query=query,
            candidate_k=candidate_k,
            final_k=final_k,
        )

        return self.context_builder.build(
            reranked_chunks
        )