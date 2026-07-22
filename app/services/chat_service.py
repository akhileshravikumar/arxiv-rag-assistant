from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.answer_generation_service import (
    AnswerGenerationService,
)
from app.services.context_builder import ContextBuilder
from app.services.retrieval_pipeline import (
    RetrievalPipeline,
)


@dataclass(frozen=True)
class ChatResult:
    question: str
    answer: str
    model: str
    sources: list[dict]
    cited_source_numbers: list[int]
    context_character_count: int
    estimated_context_tokens: int


class ChatService:
    def __init__(
        self,
        retrieval_pipeline: RetrievalPipeline,
        context_builder: ContextBuilder,
        answer_service: AnswerGenerationService,
    ) -> None:
        self.retrieval_pipeline = retrieval_pipeline
        self.context_builder = context_builder
        self.answer_service = answer_service

    def answer_question(
        self,
        db: Session,
        question: str,
        candidate_k: int = 20,
        final_k: int = 5,
    ) -> ChatResult:
        cleaned_question = question.strip()

        if not cleaned_question:
            raise ValueError(
                "Question cannot be empty."
            )

        if candidate_k < final_k:
            raise ValueError(
                "candidate_k cannot be smaller "
                "than final_k."
            )

        reranked_chunks = (
            self.retrieval_pipeline.retrieve_and_rerank(
                db=db,
                query=cleaned_question,
                candidate_k=candidate_k,
                final_k=final_k,
            )
        )

        context_result = self.context_builder.build(
            reranked_chunks
        )

        available_source_numbers = {
            chunk["source_number"]
            for chunk in context_result.included_chunks
        }

        generated_answer = (
            self.answer_service.generate_answer(
                question=cleaned_question,
                context=context_result.context,
                available_source_numbers=(
                    available_source_numbers
                ),
            )
        )

        cited_number_set = set(
            generated_answer.cited_source_numbers
        )

        sources = []

        for chunk in context_result.included_chunks:
            source_number = chunk["source_number"]

            sources.append(
                {
                    "source_number": source_number,
                    "paper_id": chunk["paper_id"],
                    "paper_title": (
                        chunk["paper_title"]
                    ),
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": (
                        chunk["chunk_index"]
                    ),
                    "reranker_rank": (
                        chunk["reranker_rank"]
                    ),
                    "reranker_score": (
                        chunk["reranker_score"]
                    ),
                    "cited_in_answer": (
                        source_number
                        in cited_number_set
                    ),
                    "text_preview": (
                        chunk["text"]
                        .replace("\n", " ")
                        [:300]
                    ),
                }
            )

        return ChatResult(
            question=cleaned_question,
            answer=generated_answer.answer,
            model=generated_answer.model,
            sources=sources,
            cited_source_numbers=(
                generated_answer.cited_source_numbers
            ),
            context_character_count=(
                context_result.character_count
            ),
            estimated_context_tokens=(
                context_result.estimated_token_count
            ),
        )