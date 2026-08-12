from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.answer_generation_service import (
    AnswerGenerationService,
)
from app.services.context_builder import ContextBuilder
from app.services.retrieval_pipeline import (
    RetrievalPipeline,
)
from app.services.cache_service import CacheService


@dataclass(frozen=True)
class ChatResult:
    question: str
    answer: str
    model: str
    sources: list[dict]
    cited_source_numbers: list[int]
    context_character_count: int
    estimated_context_tokens: int
    cache_hit: bool


class ChatService:
    def __init__(
        self,
        retrieval_pipeline: RetrievalPipeline,
        context_builder: ContextBuilder,
        answer_service: AnswerGenerationService,
        cache_service: CacheService | None = None,
    ) -> None:
        self.retrieval_pipeline = retrieval_pipeline
        self.context_builder = context_builder
        self.answer_service = answer_service
        self.cache_service = cache_service

    def answer_question(
        self,
        db: Session,
        session_id: str,
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

        # 1. Check the final-answer cache first.
        if self.cache_service is not None:
            cached_answer = self.cache_service.get_answer(
                session_id=session_id,
                question=cleaned_question,
                candidate_k=candidate_k,
                final_k=final_k,
                model=self.answer_service.model,
            )

            if cached_answer is not None:
                return ChatResult(
                    question=cached_answer["question"],
                    answer=cached_answer["answer"],
                    model=cached_answer["model"],
                    sources=cached_answer["sources"],
                    cited_source_numbers=(
                        cached_answer[
                            "cited_source_numbers"
                        ]
                    ),
                    context_character_count=(
                        cached_answer[
                            "context_character_count"
                        ]
                    ),
                    estimated_context_tokens=(
                        cached_answer[
                            "estimated_context_tokens"
                        ]
                    ),
                    cache_hit=True,
                )

        # 2. Run retrieval and reranking on a cache miss.
        reranked_chunks = (
            self.retrieval_pipeline.retrieve_and_rerank(
                db=db,
                session_id=session_id,
                query=cleaned_question,
                candidate_k=candidate_k,
                final_k=final_k,
            )
        )

        if not reranked_chunks:
            return ChatResult(
                question=cleaned_question,
                answer=(
                    "No papers have been added to this "
                    "research session yet. Add papers "
                    "before asking questions."
                ),
                model=self.answer_service.model,
                sources=[],
                cited_source_numbers=[],
                context_character_count=0,
                estimated_context_tokens=0,
                cache_hit=False,
            )

        # 3. Build bounded, citation-ready context.
        context_result = self.context_builder.build(
            reranked_chunks
        )

        available_source_numbers = {
            chunk["source_number"]
            for chunk in context_result.included_chunks
        }

        # 4. Generate the grounded answer.
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

        # 5. Build structured source metadata.
        sources: list[dict] = []

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

        result = ChatResult(
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
            cache_hit=False,
        )

        # 6. Cache the completed response.
        if self.cache_service is not None:
            self.cache_service.set_answer(
                session_id=session_id,
                question=cleaned_question,
                candidate_k=candidate_k,
                final_k=final_k,
                model=generated_answer.model,
                value={
                    "question": result.question,
                    "answer": result.answer,
                    "model": result.model,
                    "sources": result.sources,
                    "cited_source_numbers": (
                        result.cited_source_numbers
                    ),
                    "context_character_count": (
                        result.context_character_count
                    ),
                    "estimated_context_tokens": (
                        result.estimated_context_tokens
                    ),
                },
            )

        return result