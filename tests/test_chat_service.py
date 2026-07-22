from app.services.answer_generation_service import (
    GeneratedAnswer,
)
from app.services.chat_service import ChatService


class FakeRetrievalPipeline:
    def retrieve_and_rerank(
        self,
        db,
        query,
        candidate_k,
        final_k,
    ):
        return [
            {
                "chunk_id": 10,
                "paper_id": 1,
                "paper_title": "Test Paper",
                "chunk_index": 2,
                "text": "The model was evaluated on Dataset A.",
                "reranker_rank": 1,
                "reranker_score": 5.0,
            }
        ]


class FakeContextResult:
    context = (
        "[SOURCE 1]\n"
        "Paper: Test Paper\n"
        "Text: The model was evaluated on Dataset A.\n"
        "[/SOURCE 1]"
    )

    included_chunks = [
        {
            "source_number": 1,
            "chunk_id": 10,
            "paper_id": 1,
            "paper_title": "Test Paper",
            "chunk_index": 2,
            "text": (
                "The model was evaluated on Dataset A."
            ),
            "reranker_rank": 1,
            "reranker_score": 5.0,
        }
    ]

    character_count = len(context)
    estimated_token_count = 30


class FakeContextBuilder:
    def build(self, chunks):
        return FakeContextResult()


class FakeAnswerService:
    def generate_answer(
        self,
        question,
        context,
        available_source_numbers,
    ):
        return GeneratedAnswer(
            answer=(
                "The model was evaluated on Dataset A "
                "[SOURCE 1]."
            ),
            cited_source_numbers=[1],
            model="fake-model",
        )


def test_chat_service_returns_grounded_answer():
    service = ChatService(
        retrieval_pipeline=FakeRetrievalPipeline(),
        context_builder=FakeContextBuilder(),
        answer_service=FakeAnswerService(),
    )

    result = service.answer_question(
        db=None,
        question="Which dataset was used?",
        candidate_k=20,
        final_k=5,
    )

    assert "[SOURCE 1]" in result.answer
    assert result.cited_source_numbers == [1]
    assert result.sources[0]["cited_in_answer"] is True