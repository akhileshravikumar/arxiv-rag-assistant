import argparse
import sys

from app.database.database import SessionLocal
from app.services.bm25_service import BM25Service


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test BM25 keyword retrieval."
    )

    parser.add_argument(
        "query",
        help="Keyword query or exact phrase.",
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
        service = BM25Service()

        document_count = service.build_index(db)

        print(
            f"BM25 index built from "
            f"{document_count} chunks."
        )

        results = service.search(
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
                f"BM25 score: "
                f"{result['score']:.4f}"
            )
            print(
                f"Exact phrase: "
                f"{result['exact_phrase_match']}"
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
            f"BM25 search error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())