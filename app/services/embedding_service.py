import os
from collections.abc import Sequence

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from app.core.config import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
)
from app.services.cache_service import CacheService


load_dotenv()


# text-embedding-3-small accepts a `dimensions` parameter, so we can ask
# for 384 and keep the existing vector column, pgvector queries and
# cache keys unchanged while removing torch from the image entirely.

# The API accepts up to 2048 inputs per call. A five-paper session is
# roughly 250 chunks, so this batches into one or two requests.
EMBEDDING_BATCH_SIZE = 128


class EmbeddingService:
    def __init__(
        self,
        cache_service: CacheService | None = None,
        client: OpenAI | None = None,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            api_key = os.getenv(
                "OPENAI_API_KEY"
            )

            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not configured."
                )

            self.client = OpenAI(
                api_key=api_key
            )

        self.model = EMBEDDING_MODEL_NAME
        self.dimension = EMBEDDING_DIMENSION
        self.cache_service = cache_service

    def _request_embeddings(
        self,
        inputs: list[str],
    ) -> list[list[float]]:
        try:
            response = (
                self.client.embeddings.create(
                    model=self.model,
                    input=inputs,
                    dimensions=self.dimension,
                )
            )

        except OpenAIError as exc:
            raise RuntimeError(
                f"The embedding service failed: {exc}"
            ) from exc

        # The API preserves input order, but sort defensively so a
        # future change cannot silently misalign chunks and vectors.
        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )

        vectors = [
            list(item.embedding)
            for item in ordered
        ]

        for vector in vectors:
            if len(vector) != self.dimension:
                raise RuntimeError(
                    "Unexpected embedding dimension: "
                    f"expected {self.dimension}, "
                    f"received {len(vector)}."
                )

        return vectors

    def embed_text(
        self,
        text: str,
    ) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_query(
        self,
        query: str,
    ) -> list[float]:
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError(
                "Search query cannot be empty."
            )

        if self.cache_service is not None:
            cached_embedding = (
                self.cache_service
                .get_query_embedding(
                    query=cleaned_query,
                    embedding_model=self.model,
                )
            )

            if (
                cached_embedding is not None
                and len(cached_embedding)
                == self.dimension
            ):
                return cached_embedding

        vector = self._request_embeddings(
            [cleaned_query]
        )[0]

        if self.cache_service is not None:
            self.cache_service.set_query_embedding(
                query=cleaned_query,
                embedding_model=self.model,
                embedding=vector,
            )

        return vector

    def embed_documents(
        self,
        texts: Sequence[str],
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> list[list[float]]:
        if not texts:
            return []

        if batch_size < 1:
            raise ValueError(
                "batch_size must be at least 1."
            )

        cleaned_texts: list[str] = []

        for index, text in enumerate(texts):
            cleaned_text = text.strip()

            if not cleaned_text:
                raise ValueError(
                    "Cannot embed empty text at "
                    f"position {index}."
                )

            cleaned_texts.append(cleaned_text)

        embeddings: list[list[float]] = []

        for start in range(
            0,
            len(cleaned_texts),
            batch_size,
        ):
            batch = cleaned_texts[
                start : start + batch_size
            ]

            embeddings.extend(
                self._request_embeddings(batch)
            )

        if len(embeddings) != len(cleaned_texts):
            raise RuntimeError(
                "The embedding service returned the "
                "wrong number of vectors."
            )

        return embeddings
