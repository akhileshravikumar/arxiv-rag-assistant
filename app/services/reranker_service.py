import logging
import os
from collections.abc import Sequence

import httpx
from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"

RERANKER_MODEL_NAME = os.getenv(
    "RERANKER_MODEL",
    "rerank-v3.5",
)

RERANKER_TIMEOUT_SECONDS = int(
    os.getenv(
        "RERANKER_TIMEOUT_SECONDS",
        "15",
    )
)


class RerankerService:
    """
    Cross-encoder reranking over a hosted API.

    Without an API key the service degrades to a pass-through that
    preserves the incoming Reciprocal Rank Fusion order, so the whole
    pipeline still works on a deployment with no reranker configured.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = RERANKER_MODEL_NAME,
        timeout_seconds: int = (
            RERANKER_TIMEOUT_SECONDS
        ),
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("COHERE_API_KEY")
        )

        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            logger.info(
                "Reranker disabled; falling back to fusion order",
                extra={
                    "event": "reranker_disabled"
                },
            )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _finalize(
        results: list[dict],
        top_k: int,
    ) -> list[dict]:
        final_results = results[:top_k]

        for final_rank, result in enumerate(
            final_results,
            start=1,
        ):
            result["reranker_rank"] = final_rank

        return final_results

    def _fallback(
        self,
        candidates: Sequence[dict],
        top_k: int,
    ) -> list[dict]:
        results = []

        for candidate in candidates:
            result = dict(candidate)
            result["reranker_score"] = float(
                candidate.get("rrf_score", 0.0)
            )

            results.append(result)

        return self._finalize(results, top_k)

    def _request_scores(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        response = httpx.post(
            COHERE_RERANK_URL,
            headers={
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "query": query,
                "documents": documents,
                "top_n": min(
                    top_k,
                    len(documents),
                ),
            },
            timeout=self.timeout_seconds,
        )

        response.raise_for_status()

        payload = response.json()

        return [
            (
                int(item["index"]),
                float(
                    item["relevance_score"]
                ),
            )
            for item in payload.get(
                "results",
                [],
            )
        ]

    def rerank(
        self,
        query: str,
        candidates: Sequence[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Score query-chunk pairs and return the strongest chunks.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError(
                "Query cannot be empty."
            )

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1."
            )

        if not candidates:
            return []

        if not self.enabled:
            return self._fallback(
                candidates,
                top_k,
            )

        documents = [
            candidate["text"]
            for candidate in candidates
        ]

        try:
            scored = self._request_scores(
                query=cleaned_query,
                documents=documents,
                top_k=top_k,
            )

        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
        ) as exc:
            # Reranking is a quality improvement, not a hard
            # requirement. A reranker outage should not take down chat.
            logger.warning(
                "Reranker request failed; using fusion order",
                extra={
                    "event": "reranker_failed",
                    "error": str(exc),
                },
            )

            return self._fallback(
                candidates,
                top_k,
            )

        results: list[dict] = []

        for index, score in scored:
            if index < 0 or index >= len(
                candidates
            ):
                continue

            result = dict(candidates[index])
            result["reranker_score"] = score

            results.append(result)

        if not results:
            return self._fallback(
                candidates,
                top_k,
            )

        results.sort(
            key=lambda result: result[
                "reranker_score"
            ],
            reverse=True,
        )

        return self._finalize(results, top_k)
