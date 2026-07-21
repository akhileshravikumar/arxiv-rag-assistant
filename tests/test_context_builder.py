from app.services.context_builder import ContextBuilder


def create_chunk(
    chunk_id: int,
    text: str,
    score: float = 1.0,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "paper_id": 1,
        "paper_title": "Test Paper",
        "chunk_index": chunk_id - 1,
        "text": text,
        "reranker_score": score,
    }


def test_context_contains_metadata():
    builder = ContextBuilder(
        max_context_characters=5_000,
        max_chunk_characters=1_000,
    )

    result = builder.build(
        [
            create_chunk(
                chunk_id=1,
                text="Relevant research text.",
            )
        ]
    )

    assert "[SOURCE 1]" in result.context
    assert "Paper: Test Paper" in result.context
    assert "Chunk ID: 1" in result.context
    assert "Relevant research text." in result.context


def test_context_respects_character_limit():
    builder = ContextBuilder(
        max_context_characters=500,
        max_chunk_characters=300,
    )

    chunks = [
        create_chunk(1, "A" * 300),
        create_chunk(2, "B" * 300),
    ]

    result = builder.build(chunks)

    assert result.character_count <= 500
    assert len(result.skipped_chunks) >= 1


def test_empty_chunks_are_skipped():
    builder = ContextBuilder()

    result = builder.build(
        [
            create_chunk(1, "   "),
            create_chunk(2, "Useful text."),
        ]
    )

    assert len(result.included_chunks) == 1
    assert len(result.skipped_chunks) == 1


def test_chunk_text_is_truncated():
    builder = ContextBuilder(
        max_context_characters=2_000,
        max_chunk_characters=100,
    )

    result = builder.build(
        [
            create_chunk(
                chunk_id=1,
                text="A" * 500,
            )
        ]
    )

    assert "A" * 100 in result.context
    assert "A" * 101 not in result.context