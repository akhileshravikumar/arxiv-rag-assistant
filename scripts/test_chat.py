import argparse
import sys

from app.database.database import SessionLocal
from app.services.answer_generation_service import (
    AnswerGenerationService,
)
from app.services.bm25_service import BM25Service
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from app.services.reranker_service import RerankerService
from app.services.retrieval_pipeline import RetrievalPipeline
from app.services.retrieval_service import RetrievalService


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete RAG question-answering pipeline."
        )
    )

    parser.add_argument(
        "question",
        help="Question to answer.",
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

        reranker_service = RerankerService()

        context_builder = ContextBuilder(
            max_context_characters=12_000,
            max_chunk_characters=3_000,
        )

        retrieval_pipeline = RetrievalPipeline(
            hybrid_service=hybrid_service,
            reranker_service=reranker_service,
            context_builder=context_builder,
            candidate_k=arguments.candidate_k,
            final_k=arguments.final_k,
        )

        answer_service = AnswerGenerationService()

        chat_service = ChatService(
            retrieval_pipeline=retrieval_pipeline,
            context_builder=context_builder,
            answer_service=answer_service,
        )

        result = chat_service.answer_question(
            db=db,
            question=arguments.question,
            candidate_k=arguments.candidate_k,
            final_k=arguments.final_k,
        )

        print()
        print("=== QUESTION ===")
        print(result.question)

        print()
        print("=== ANSWER ===")
        print(result.answer)

        print()
        print("=== SOURCES ===")

        for source in result.sources:
            print()
            print(
                f"[SOURCE {source['source_number']}]"
            )
            print(
                f"Paper: {source['paper_title']}"
            )
            print(
                f"Paper ID: {source['paper_id']}"
            )
            print(
                f"Chunk ID: {source['chunk_id']}"
            )
            print(
                f"Chunk index: "
                f"{source['chunk_index']}"
            )
            print(
                f"Cited: "
                f"{source['cited_in_answer']}"
            )
            print(
                f"Preview: "
                f"{source['text_preview']}"
            )

        print()
        print("=== PIPELINE METADATA ===")
        print(f"Model: {result.model}")
        print(
            f"Cited sources: "
            f"{result.cited_source_numbers}"
        )
        print(
            f"Context characters: "
            f"{result.context_character_count}"
        )
        print(
            f"Estimated context tokens: "
            f"{result.estimated_context_tokens}"
        )

        return 0

    except Exception as exc:
        print(
            f"Chat error: {exc}",
            file=sys.stderr,
        )
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())