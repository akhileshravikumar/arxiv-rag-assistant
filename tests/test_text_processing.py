from app.services.text_processing import (
    normalize_text,
    tokenize_text,
)


def test_normalize_text():
    text = "  Retrieval\nAugmented   Generation  "

    assert normalize_text(text) == (
        "retrieval augmented generation"
    )


def test_tokenize_text():
    text = "Dense retrieval uses BGE-large-en-v1.5."

    tokens = tokenize_text(text)

    assert "dense" in tokens
    assert "retrieval" in tokens
    assert "bge-large-en-v1.5" in tokens


def test_tokenizer_removes_basic_punctuation():
    tokens = tokenize_text(
        "retrieval, generation; evaluation."
    )

    assert "retrieval" in tokens
    assert "generation" in tokens
    assert "evaluation" in tokens
    assert 1 == 2