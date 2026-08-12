import os
import re
from dataclasses import dataclass

from openai import OpenAI


CITATION_PATTERN = re.compile(
    r"\[SOURCE\s+(\d+)\]",
    re.IGNORECASE,
)


RAG_INSTRUCTIONS = """
You are an academic research assistant answering questions from
retrieved research-paper passages.

Follow these rules strictly:

1. Answer using only the information in the supplied sources.
2. Do not use outside knowledge, assumptions, or unsupported facts.
3. Cite every factual claim using one or more citations such as
   [SOURCE 1] or [SOURCE 2].
4. Use only source numbers that appear in the supplied context.
5. Place citations immediately after the claim they support.
6. Do not invent paper titles, authors, experiments, metrics, or results.
7. If the sources do not contain enough information, say:
   "The retrieved sources do not provide enough information to answer
   this question."
8. If sources partially answer the question, clearly state what is
   supported and what remains unavailable.
9. Keep the answer direct and readable.
10. Do not include a separate bibliography. The application will attach
    structured paper and chunk metadata.
"""


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    cited_source_numbers: list[int]
    model: str


class AnswerGenerationService:
    def __init__(
        self,
        model: str | None = None,
    ) -> None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        self.model = (
            model
            or os.getenv("OPENAI_MODEL")
            or "gpt-4.1-mini"
        )

        # Only reasoning models accept a reasoning effort. Leave this
        # unset for gpt-4.1-class models or the request is rejected.
        self.reasoning_effort = (
            os.getenv(
                "OPENAI_REASONING_EFFORT",
                "",
            ).strip()
            or None
        )

        self.client = OpenAI(
            api_key=api_key
        )

    @staticmethod
    def extract_citation_numbers(
        answer: str,
    ) -> list[int]:
        """
        Extract unique source numbers in answer order.
        """
        citation_numbers: list[int] = []

        for match in CITATION_PATTERN.finditer(answer):
            source_number = int(match.group(1))

            if source_number not in citation_numbers:
                citation_numbers.append(source_number)

        return citation_numbers

    @staticmethod
    def validate_citations(
        citation_numbers: list[int],
        available_source_numbers: set[int],
    ) -> None:
        invalid_numbers = [
            number
            for number in citation_numbers
            if number not in available_source_numbers
        ]

        if invalid_numbers:
            raise RuntimeError(
                "The LLM produced invalid source citations: "
                f"{invalid_numbers}"
            )

    def generate_answer(
        self,
        question: str,
        context: str,
        available_source_numbers: set[int],
    ) -> GeneratedAnswer:
        cleaned_question = question.strip()

        if not cleaned_question:
            raise ValueError(
                "Question cannot be empty."
            )

        if not context.strip():
            return GeneratedAnswer(
                answer=(
                    "The retrieved sources do not provide "
                    "enough information to answer this question."
                ),
                cited_source_numbers=[],
                model=self.model,
            )

        model_input = (
            "Answer the question using only the source context.\n\n"
            f"QUESTION:\n{cleaned_question}\n\n"
            f"SOURCE CONTEXT:\n{context}"
        )

        request_options: dict = {
            "model": self.model,
            "instructions": RAG_INSTRUCTIONS,
            "input": model_input,
            "max_output_tokens": 800,
        }

        if self.reasoning_effort:
            request_options["reasoning"] = {
                "effort": self.reasoning_effort,
            }

        response = self.client.responses.create(
            **request_options
        )

        answer = response.output_text.strip()

        if not answer:
            raise RuntimeError(
                "The LLM returned an empty answer."
            )

        citation_numbers = (
            self.extract_citation_numbers(answer)
        )

        self.validate_citations(
            citation_numbers=citation_numbers,
            available_source_numbers=(
                available_source_numbers
            ),
        )

        return GeneratedAnswer(
            answer=answer,
            cited_source_numbers=(
                citation_numbers
            ),
            model=self.model,
        )