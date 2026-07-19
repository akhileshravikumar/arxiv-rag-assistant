import argparse
import sys

from app.database.database import SessionLocal
from app.services.bm25_service import BM25Service
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare BM25 keyword retrieval "
            "with dense vector retrieval."
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


def print_dense_results(
    results: list[dict],
) -> None:
    print()
    print("=== DENSE RETRIEVAL ===")

    for rank, result in enumerate(
        results,
        start=1,
    ):
        preview = (
            result["text"]
            .replace("\n", " ")
            [:180]
        )

        print(
            f"{rank}. "
            f"similarity={result['similarity']:.4f} | "
            f"chunk={result['chunk_id']} | "
            f"paper={result['paper_title']}"
        )
        print(f"   {preview}...")


def print_bm25_results(
    results: list[dict],
) -> None:
    print()
    print("=== BM25 RETRIEVAL ===")

    for rank, result in enumerate(
        results,
        start=1,
    ):
        preview = (
            result["text"]
            .replace("\n", " ")
            [:180]
        )

        print(
            f"{rank}. "
            f"score={result['score']:.4f} | "
            f"phrase={result['exact_phrase_match']} | "
            f"chunk={result['chunk_id']} | "
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

        dense_results = dense_service.dense_search(
            db=db,
            query=arguments.query,
            top_k=arguments.top_k,
        )

        bm25_results = bm25_service.search(
            query=arguments.query,
            top_k=arguments.top_k,
        )

        print(f"Query: {arguments.query}")

        print_dense_results(dense_results)
        print_bm25_results(bm25_results)

        dense_ids = {
            result["chunk_id"]
            for result in dense_results
        }

        bm25_ids = {
            result["chunk_id"]
            for result in bm25_results
        }

        shared_ids = dense_ids & bm25_ids

        print()
        print(
            f"Shared chunks in both top-{arguments.top_k}: "
            f"{len(shared_ids)}"
        )
        print(
            f"Shared chunk IDs: "
            f"{sorted(shared_ids)}"
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