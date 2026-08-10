from collections.abc import Sequence

from sentence_transformers import CrossEncoder


# Small cross-encoder for the free-tier hosted deployment (~90MB vs
# ~1.3GB for bge-reranker-large), to keep total memory under Render's
# free 512MB instance limit.
RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RerankerService:
    def __init__(
        self,
        model_name: str = RERANKER_MODEL_NAME,
        max_length: int = 512,
        device: str | None = None,
    ) -> None:
        print(f"Loading reranker model: {model_name}")

        self.model = CrossEncoder(
            model_name,
            max_length=max_length,
            device=device,
        )

        print("Reranker model loaded.")

    def rerank(
        self,
        query: str,
        candidates: Sequence[dict],
        top_k: int = 5,
        batch_size: int = 8,
    ) -> list[dict]:
        """
        Score query–chunk pairs and return the strongest chunks.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Query cannot be empty.")

        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        if batch_size < 1:
            raise ValueError(
                "batch_size must be at least 1."
            )

        if not candidates:
            return []

        pairs = [
            [cleaned_query, candidate["text"]]
            for candidate in candidates
        ]

        scores = self.model.predict(
            pairs,
            batch_size=batch_size,
            show_progress_bar=False,
        )

        if len(scores) != len(candidates):
            raise RuntimeError(
                "Reranker returned an unexpected "
                "number of scores."
            )

        reranked_results: list[dict] = []

        for candidate, score in zip(
            candidates,
            scores,
            strict=True,
        ):
            result = dict(candidate)
            result["reranker_score"] = float(score)

            reranked_results.append(result)

        reranked_results.sort(
            key=lambda result: result["reranker_score"],
            reverse=True,
        )

        final_results = reranked_results[:top_k]

        for final_rank, result in enumerate(
            final_results,
            start=1,
        ):
            result["reranker_rank"] = final_rank

        return final_results