from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBuildResult:
    context: str
    included_chunks: list[dict]
    skipped_chunks: list[dict]
    character_count: int
    estimated_token_count: int


class ContextBuilder:
    def __init__(
        self,
        max_context_characters: int = 12_000,
        max_chunk_characters: int = 3_000,
    ) -> None:
        if max_context_characters < 1:
            raise ValueError(
                "max_context_characters must be positive."
            )

        if max_chunk_characters < 1:
            raise ValueError(
                "max_chunk_characters must be positive."
            )

        self.max_context_characters = (
            max_context_characters
        )
        self.max_chunk_characters = (
            max_chunk_characters
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Temporary approximation until the generation
        model's exact tokenizer is introduced.
        """
        return max(1, (len(text) + 3) // 4)

    def build(
    self,
        chunks: list[dict],
    ) -> ContextBuildResult:
        
        context_sections: list[str] = []
        included_chunks: list[dict] = []
        skipped_chunks: list[dict] = []

        current_length = 0

        for chunk in chunks:
            chunk_text = chunk["text"].strip()

            if not chunk_text:
                skipped_chunks.append(
                    {
                        **chunk,
                        "skip_reason": "empty_text",
                    }
                )
                continue

            source_number = len(included_chunks) + 1

            truncated_text = chunk_text[
                : self.max_chunk_characters
            ]

            section = (
                f"[SOURCE {source_number}]\n"
                f"Paper: {chunk['paper_title']}\n"
                f"Paper ID: {chunk['paper_id']}\n"
                f"Chunk ID: {chunk['chunk_id']}\n"
                f"Chunk index: {chunk['chunk_index']}\n"
                f"Text:\n{truncated_text}\n"
                f"[/SOURCE {source_number}]"
            )

            separator_length = (
                2 if context_sections else 0
            )

            projected_length = (
                current_length
                + separator_length
                + len(section)
            )

            if (
                projected_length
                > self.max_context_characters
            ):
                skipped_chunks.append(
                    {
                        **chunk,
                        "skip_reason": (
                            "context_budget_exceeded"
                        ),
                    }
                )
                continue

            included_chunk = {
                **chunk,
                "source_number": source_number,
            }

            context_sections.append(section)
            included_chunks.append(included_chunk)
            current_length = projected_length

        context = "\n\n".join(context_sections)

        return ContextBuildResult(
            context=context,
            included_chunks=included_chunks,
            skipped_chunks=skipped_chunks,
            character_count=len(context),
            estimated_token_count=(
                self.estimate_tokens(context)
                if context
                else 0
            ),
        )