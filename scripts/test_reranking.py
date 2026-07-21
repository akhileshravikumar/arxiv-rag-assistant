import argparse
import sys

from app.database.database import SessionLocal
from app.services.bm25_service import BM25Service
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from app.services.reranker_service import RerankerService
from app.services.retrieval_pipeline import RetrievalPipeline
from app.services.retrieval_service import RetrievalService

from app.services.context_builder import ContextBuilder


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve hybrid candidates and rerank them."
        )
    )

    parser.add_argument(
        "query",
        help="Question to search for.",
    )

    parser.add_argument(
        "--candidate-k",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--final-k",
        type=int,
        default=5,
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
        bm25_service.build_index(db)

        hybrid_service = HybridRetrievalService(
            dense_service=dense_service,
            bm25_service=bm25_service,
        )

        context_builder = ContextBuilder(
            max_context_characters=12_000,
            max_chunk_characters=3_000,
        )

        reranker_service = RerankerService()

        pipeline = RetrievalPipeline(
            hybrid_service=hybrid_service,
            reranker_service=reranker_service,
            context_builder=context_builder,
            candidate_k=arguments.candidate_k,
            final_k=arguments.final_k,
        )

        results = pipeline.retrieve_and_rerank(
            db=db,
            query=arguments.query,
        )

        print()
        print(f"Query: {arguments.query}")
        print(
            f"Retrieved candidates: "
            f"{arguments.candidate_k}"
        )
        print(f"Final results: {len(results)}")

        for result in results:
            preview = (
                result["text"]
                .replace("\n", " ")
                [:300]
            )

            print()
            print(
                f"Reranker rank: "
                f"{result['reranker_rank']}"
            )
            print(
                f"Reranker score: "
                f"{result['reranker_score']:.6f}"
            )
            print(
                f"Previous RRF score: "
                f"{result['rrf_score']}"
            )
            print(
                f"Sources: "
                f"{result['retrieval_sources']}"
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

            context_result = (
                pipeline.retrieve_rerank_and_build_context(
                    db=db,
                    query=arguments.query,
                )
            )

            print()
            print("=== CONTEXT SUMMARY ===")
            print(
                f"Included chunks: "
                f"{len(context_result.included_chunks)}"
            )
            print(
                f"Skipped chunks: "
                f"{len(context_result.skipped_chunks)}"
            )
            print(
                f"Context characters: "
                f"{context_result.character_count}"
            )
            print(
                f"Estimated tokens: "
                f"{context_result.estimated_token_count}"
            )

            print()
            print("=== GENERATED CONTEXT ===")
            print(context_result.context)

        return 0

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        print(
            f"Reranking error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())