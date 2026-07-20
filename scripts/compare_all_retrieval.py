import argparse
import sys

from app.database.database import SessionLocal
from app.services.bm25_service import BM25Service
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from app.services.retrieval_service import RetrievalService


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare dense, BM25 and hybrid retrieval."
        )
    )

    parser.add_argument(
        "query",
        help="Search query.",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )

    return parser.parse_args()


def print_results(
    heading: str,
    results: list[dict],
    score_key: str,
) -> None:
    print()
    print(f"=== {heading} ===")

    for rank, result in enumerate(
        results,
        start=1,
    ):
        preview = (
            result["text"]
            .replace("\n", " ")
            [:150]
        )

        print(
            f"{rank}. "
            f"chunk={result['chunk_id']} | "
            f"{score_key}={result[score_key]} | "
            f"paper={result['paper_title']}"
        )
        print(f"   {preview}...")


def main() -> int:
    arguments = parse_arguments()

    db = SessionLocal()

    try:
        embedding_service = EmbeddingService()

        dense_service = RetrievalService(
            embedding_service=embedding_service
        )

        bm25_service = BM25Service()
        bm25_service.build_index(db)

        hybrid_service = HybridRetrievalService(
            dense_service=dense_service,
            bm25_service=bm25_service,
        )

        dense_results = dense_service.dense_search(
            db=db,
            query=arguments.query,
            top_k=arguments.top_k,
        )

        bm25_results = bm25_service.search(
            query=arguments.query,
            top_k=arguments.top_k,
        )

        hybrid_results = hybrid_service.hybrid_search(
            db=db,
            query=arguments.query,
            top_k=arguments.top_k,
        )

        print(f"Query: {arguments.query}")

        print_results(
            "DENSE",
            dense_results,
            "similarity",
        )

        print_results(
            "BM25",
            bm25_results,
            "score",
        )

        print_results(
            "HYBRID RRF",
            hybrid_results,
            "rrf_score",
        )

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"Comparison error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())