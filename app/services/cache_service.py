import os
from typing import Any

from dotenv import load_dotenv

from app.services.cache_key_service import (
    CacheKeyService,
)
from app.services.redis_service import RedisService


load_dotenv()


ANSWER_CACHE_TTL_SECONDS = int(
    os.getenv(
        "ANSWER_CACHE_TTL_SECONDS",
        "3600",
    )
)

QUERY_EMBEDDING_CACHE_TTL_SECONDS = int(
    os.getenv(
        "QUERY_EMBEDDING_CACHE_TTL_SECONDS",
        "86400",
    )
)


class CacheService:
    def __init__(
        self,
        redis_service: RedisService,
        key_service: CacheKeyService,
    ) -> None:
        self.redis_service = redis_service
        self.key_service = key_service

    def get_corpus_version(
        self,
        session_id: str,
    ) -> int:
        return self.redis_service.get_integer(
            self.key_service.corpus_version_key(
                session_id
            ),
            default=0,
        )

    def increment_corpus_version(
        self,
        session_id: str,
    ) -> int:
        """
        Logically invalidate a session's answer cache after ingestion.
        """
        try:
            return self.redis_service.increment(
                self.key_service.corpus_version_key(
                    session_id
                )
            )
        except RuntimeError:
            # A cache outage must not fail an otherwise good ingestion.
            return 0

    def get_answer(
        self,
        *,
        session_id: str,
        question: str,
        candidate_k: int,
        final_k: int,
        model: str,
    ) -> dict[str, Any] | None:
        corpus_version = (
            self.get_corpus_version(session_id)
        )

        key = self.key_service.answer_key(
            session_id=session_id,
            question=question,
            candidate_k=candidate_k,
            final_k=final_k,
            model=model,
            corpus_version=corpus_version,
        )

        value = self.redis_service.get_json(
            key
        )

        if isinstance(value, dict):
            return value

        return None

    def set_answer(
        self,
        *,
        session_id: str,
        question: str,
        candidate_k: int,
        final_k: int,
        model: str,
        value: dict[str, Any],
    ) -> bool:
        corpus_version = (
            self.get_corpus_version(session_id)
        )

        key = self.key_service.answer_key(
            session_id=session_id,
            question=question,
            candidate_k=candidate_k,
            final_k=final_k,
            model=model,
            corpus_version=corpus_version,
        )

        return self.redis_service.set_json(
            key=key,
            value=value,
            ttl_seconds=(
                ANSWER_CACHE_TTL_SECONDS
            ),
        )

    def get_query_embedding(
        self,
        *,
        query: str,
        embedding_model: str,
    ) -> list[float] | None:
        key = (
            self.key_service
            .query_embedding_key(
                query=query,
                embedding_model=embedding_model,
            )
        )

        value = self.redis_service.get_json(
            key
        )

        if not isinstance(value, list):
            return None

        try:
            return [
                float(item)
                for item in value
            ]
        except (
            TypeError,
            ValueError,
        ):
            return None

    def set_query_embedding(
        self,
        *,
        query: str,
        embedding_model: str,
        embedding: list[float],
    ) -> bool:
        key = (
            self.key_service
            .query_embedding_key(
                query=query,
                embedding_model=embedding_model,
            )
        )

        return self.redis_service.set_json(
            key=key,
            value=embedding,
            ttl_seconds=(
                QUERY_EMBEDDING_CACHE_TTL_SECONDS
            ),
        )