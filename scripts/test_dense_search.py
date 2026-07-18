import argparse
import sys

from app.database.database import SessionLocal
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test dense vector retrieval."
    )

    parser.add_argument(
        "query",
        help="Question or search text.",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results to return. Default: 5",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    db = SessionLocal()

    try:
        embedding_service = EmbeddingService()

        retrieval_service = RetrievalService(
            embedding_service=embedding_service
        )

        results = retrieval_service.dense_search(
            db=db,
            query=arguments.query,
            top_k=arguments.top_k,
        )

        print()
        print(f"Query: {arguments.query}")
        print(f"Results: {len(results)}")

        for rank, result in enumerate(
            results,
            start=1,
        ):
            preview = (
                result["text"]
                .replace("\n", " ")
                [:300]
            )

            print()
            print(f"Rank: {rank}")
            print(
                f"Similarity: "
                f"{result['similarity']:.4f}"
            )
            print(
                f"Paper: "
                f"{result['paper_title']}"
            )
            print(
                f"Chunk: "
                f"{result['chunk_index']}"
            )
            print(f"Preview: {preview}...")

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"Search error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())