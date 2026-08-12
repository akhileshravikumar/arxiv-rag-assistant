from app.services.cache_key_service import (
    CacheKeyService,
)


def build_key(
    service: CacheKeyService,
    **overrides,
) -> str:
    payload = {
        "session_id": "session-a",
        "question": "What is RAG?",
        "candidate_k": 20,
        "final_k": 5,
        "model": "test-model",
        "corpus_version": 1,
    }

    payload.update(overrides)

    return service.answer_key(**payload)


def test_same_normalized_question_has_same_key():
    service = CacheKeyService()

    first = build_key(service)

    second = build_key(
        service,
        question="  WHAT   IS RAG? ",
    )

    assert first == second


def test_different_sessions_never_share_answers():
    service = CacheKeyService()

    first = build_key(service)

    second = build_key(
        service,
        session_id="session-b",
    )

    assert first != second


def test_corpus_version_changes_answer_key():
    service = CacheKeyService()

    assert build_key(service) != build_key(
        service,
        corpus_version=2,
    )


def test_final_k_changes_answer_key():
    service = CacheKeyService()

    assert build_key(service) != build_key(
        service,
        final_k=8,
    )


def test_corpus_version_key_is_per_session():
    service = CacheKeyService()

    assert service.corpus_version_key(
        "session-a"
    ) != service.corpus_version_key("session-b")
