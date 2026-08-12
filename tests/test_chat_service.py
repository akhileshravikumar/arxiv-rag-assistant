from app.services.answer_generation_service import (
    GeneratedAnswer,
)
from app.services.chat_service import ChatService


CHUNK = {
    "chunk_id": 10,
    "paper_id": 1,
    "paper_title": "Test Paper",
    "chunk_index": 2,
    "text": "The model was evaluated on Dataset A.",
    "reranker_rank": 1,
    "reranker_score": 5.0,
}


class FakeRetrievalPipeline:
    def __init__(self, chunks=None):
        self.chunks = (
            [CHUNK] if chunks is None else chunks
        )

        self.session_ids: list[str] = []

    def retrieve_and_rerank(
        self,
        db,
        session_id,
        query,
        candidate_k,
        final_k,
    ):
        self.session_ids.append(session_id)

        return self.chunks


class FakeContextResult:
    context = (
        "[SOURCE 1]\n"
        "Paper: Test Paper\n"
        "Text: The model was evaluated on Dataset A.\n"
        "[/SOURCE 1]"
    )

    included_chunks = [
        {
            **CHUNK,
            "source_number": 1,
        }
    ]

    character_count = len(context)
    estimated_token_count = 30


class FakeContextBuilder:
    def build(self, chunks):
        return FakeContextResult()


class FakeAnswerService:
    model = "fake-model"

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


class FakeCacheService:
    def __init__(self):
        self.values: dict[str, dict] = {}

    def get_answer(self, *, session_id, **kwargs):
        return self.values.get(session_id)

    def set_answer(
        self,
        *,
        session_id,
        value,
        **kwargs,
    ):
        self.values[session_id] = value

        return True


def build_service(
    cache_service=None,
    pipeline=None,
) -> ChatService:
    return ChatService(
        retrieval_pipeline=(
            pipeline or FakeRetrievalPipeline()
        ),
        context_builder=FakeContextBuilder(),
        answer_service=FakeAnswerService(),
        cache_service=cache_service,
    )


def test_chat_service_returns_grounded_answer():
    service = build_service()

    result = service.answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
        candidate_k=20,
        final_k=5,
    )

    assert "[SOURCE 1]" in result.answer
    assert result.cited_source_numbers == [1]
    assert result.sources[0]["cited_in_answer"] is True
    assert result.cache_hit is False


def test_session_id_reaches_the_retrieval_pipeline():
    pipeline = FakeRetrievalPipeline()

    build_service(pipeline=pipeline).answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
    )

    assert pipeline.session_ids == ["session-a"]


def test_second_chat_request_uses_cache():
    service = build_service(
        cache_service=FakeCacheService()
    )

    first = service.answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
    )

    second = service.answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.answer == second.answer


def test_cache_is_not_shared_between_sessions():
    service = build_service(
        cache_service=FakeCacheService()
    )

    service.answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
    )

    other = service.answer_question(
        db=None,
        session_id="session-b",
        question="Which dataset was used?",
    )

    assert other.cache_hit is False


def test_empty_session_returns_a_helpful_answer():
    service = build_service(
        pipeline=FakeRetrievalPipeline(chunks=[])
    )

    result = service.answer_question(
        db=None,
        session_id="session-a",
        question="Which dataset was used?",
    )

    assert result.sources == []
    assert "No papers" in result.answer
