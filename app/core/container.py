from dataclasses import dataclass

from app.services.answer_generation_service import (
    AnswerGenerationService,
)
from app.services.bm25_service import BM25Service
from app.services.cache_key_service import CacheKeyService
from app.services.cache_service import CacheService
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from app.services.ingestion_service import IngestionService
from app.services.job_service import JobService
from app.services.reranker_service import RerankerService
from app.services.retrieval_pipeline import RetrievalPipeline
from app.services.retrieval_service import RetrievalService
from app.services.session_service import SessionService
from app.services.redis_service import redis_service


@dataclass
class ServiceContainer:
    cache_service: CacheService
    session_service: SessionService
    job_service: JobService
    embedding_service: EmbeddingService
    retrieval_service: RetrievalService
    bm25_service: BM25Service
    hybrid_retrieval_service: HybridRetrievalService
    reranker_service: RerankerService
    context_builder: ContextBuilder
    retrieval_pipeline: RetrievalPipeline
    answer_generation_service: AnswerGenerationService
    chat_service: ChatService
    ingestion_service: IngestionService


def build_container() -> ServiceContainer:
    """
    Wire every service once at application startup.

    Nothing here loads a model, so startup is fast enough to survive the
    port-scan window on a cold free-tier instance.
    """
    cache_service = CacheService(
        redis_service=redis_service,
        key_service=CacheKeyService(),
    )

    session_service = SessionService()

    job_service = JobService(
        redis_service=redis_service
    )

    embedding_service = EmbeddingService(
        cache_service=cache_service
    )

    retrieval_service = RetrievalService(
        embedding_service=embedding_service
    )

    bm25_service = BM25Service()

    hybrid_retrieval_service = (
        HybridRetrievalService(
            dense_service=retrieval_service,
            bm25_service=bm25_service,
        )
    )

    reranker_service = RerankerService()

    context_builder = ContextBuilder(
        max_context_characters=12_000,
        max_chunk_characters=3_000,
    )

    retrieval_pipeline = RetrievalPipeline(
        hybrid_service=hybrid_retrieval_service,
        reranker_service=reranker_service,
        context_builder=context_builder,
        candidate_k=20,
        final_k=5,
    )

    answer_generation_service = (
        AnswerGenerationService()
    )

    chat_service = ChatService(
        retrieval_pipeline=retrieval_pipeline,
        context_builder=context_builder,
        answer_service=answer_generation_service,
        cache_service=cache_service,
    )

    ingestion_service = IngestionService(
        embedding_service=embedding_service
    )

    return ServiceContainer(
        cache_service=cache_service,
        session_service=session_service,
        job_service=job_service,
        embedding_service=embedding_service,
        retrieval_service=retrieval_service,
        bm25_service=bm25_service,
        hybrid_retrieval_service=(
            hybrid_retrieval_service
        ),
        reranker_service=reranker_service,
        context_builder=context_builder,
        retrieval_pipeline=retrieval_pipeline,
        answer_generation_service=(
            answer_generation_service
        ),
        chat_service=chat_service,
        ingestion_service=ingestion_service,
    )
