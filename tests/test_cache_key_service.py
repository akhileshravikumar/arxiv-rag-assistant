from app.services.cache_key_service import (
    CacheKeyService,
)


def test_same_normalized_question_has_same_key():
    service = CacheKeyService()

    first = service.answer_key(
        question="What is RAG?",
        candidate_k=20,
        final_k=5,
        model="test-model",
        corpus_version=1,
    )

    second = service.answer_key(
        question="  WHAT   IS RAG? ",
        candidate_k=20,
        final_k=5,
        model="test-model",
        corpus_version=1,
    )

    assert first == second


def test_corpus_version_changes_answer_key():
    service = CacheKeyService()

    first = service.answer_key(
        question="What is RAG?",
        candidate_k=20,
        final_k=5,
        model="test-model",
        corpus_version=1,
    )

    second = service.answer_key(
        question="What is RAG?",
        candidate_k=20,
        final_k=5,
        model="test-model",
        corpus_version=2,
    )

    assert first != second


def test_final_k_changes_answer_key():
    service = CacheKeyService()

    first = service.answer_key(
        question="What is RAG?",
        candidate_k=20,
        final_k=5,
        model="test-model",
        corpus_version=1,
    )

    second = service.answer_key(
        question="What is RAG?",
        candidate_k=20,
        final_k=8,
        model="test-model",
        corpus_version=1,
    )

    assert first != second