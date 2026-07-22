import pytest

from app.services.answer_generation_service import (
    AnswerGenerationService,
)


def test_extract_citation_numbers():
    answer = (
        "The method uses retrieval [SOURCE 2]. "
        "It was evaluated experimentally "
        "[SOURCE 1] [SOURCE 2]."
    )

    result = (
        AnswerGenerationService
        .extract_citation_numbers(answer)
    )

    assert result == [2, 1]


def test_duplicate_citations_are_removed():
    answer = (
        "Claim one [SOURCE 1]. "
        "Claim two [SOURCE 1]."
    )

    result = (
        AnswerGenerationService
        .extract_citation_numbers(answer)
    )

    assert result == [1]


def test_invalid_citation_is_rejected():
    with pytest.raises(
        RuntimeError,
        match="invalid source citations",
    ):
        (
            AnswerGenerationService
            .validate_citations(
                citation_numbers=[1, 7],
                available_source_numbers={
                    1,
                    2,
                    3,
                },
            )
        )


def test_valid_citations_pass():
    AnswerGenerationService.validate_citations(
        citation_numbers=[1, 3],
        available_source_numbers={
            1,
            2,
            3,
        },
    )