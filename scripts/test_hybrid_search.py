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
            "Test hybrid retrieval using dense search, "
            "BM25 and Reciprocal Rank Fusion."
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
        help="Final number of results. Default: 5",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    db = SessionLocal()

    try:
        embedding_service = EmbeddingService()

        dense_service = RetrievalService(
            embedding_service=embedding_service
        )

        bm25_service = BM25Service()
        indexed_count = bm25_service.build_index(db)

        hybrid_service = HybridRetrievalService(
            dense_service=dense_service,
            bm25_service=bm25_service,
        )

        results = hybrid_service.hybrid_search(
            db=db,
            query=arguments.query,
            top_k=arguments.top_k,
        )

        print(
            f"BM25 index contains "
            f"{indexed_count} chunks."
        )
        print(f"Query: {arguments.query}")
        print(f"Final results: {len(results)}")

        for rank, result in enumerate(
            results,
            start=1,
        ):
            preview = (
                result["text"]
                .replace("\n", " ")
                [:250]
            )

            print()
            print(f"Final rank: {rank}")
            print(
                f"RRF score: "
                f"{result['rrf_score']:.8f}"
            )
            print(
                f"Sources: "
                f"{', '.join(result['retrieval_sources'])}"
            )
            print(
                f"Dense rank: "
                f"{result['dense_rank']}"
            )
            print(
                f"Dense similarity: "
                f"{result['dense_similarity']}"
            )
            print(
                f"BM25 rank: "
                f"{result['bm25_rank']}"
            )
            print(
                f"BM25 score: "
                f"{result['bm25_score']}"
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
                f"Chunk ID: "
                f"{result['chunk_id']}"
            )
            print(
                f"Chunk index: "
                f"{result['chunk_index']}"
            )
            print(f"Preview: {preview}...")

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"Hybrid search error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())