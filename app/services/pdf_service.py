from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class PDFExtractionResult:
    pdf_path: Path
    text: str
    page_count: int
    character_count: int
    word_count: int
    pages_without_text: list[int]


def count_words(text: str) -> int:
    return len(text.split())


def extract_text_from_pdf(
    pdf_path: Path,
) -> PDFExtractionResult:
    resolved_path = (
        pdf_path.expanduser().resolve()
    )

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"PDF does not exist: {resolved_path}"
        )

    if not resolved_path.is_file():
        raise ValueError(
            "The supplied path is not a file: "
            f"{resolved_path}"
        )

    if resolved_path.suffix.lower() != ".pdf":
        raise ValueError(
            "The supplied file is not a PDF: "
            f"{resolved_path.name}"
        )

    page_texts: list[str] = []
    pages_without_text: list[int] = []

    try:
        with pymupdf.open(
            resolved_path
        ) as document:
            if document.needs_pass:
                raise PermissionError(
                    "The PDF is password-protected "
                    "and cannot be read."
                )

            page_count = document.page_count

            if page_count == 0:
                raise ValueError(
                    "The PDF contains no pages."
                )

            for page_number, page in enumerate(
                document,
                start=1,
            ):
                page_text = page.get_text(
                    "text",
                    sort=True,
                ).strip()

                if not page_text:
                    pages_without_text.append(
                        page_number
                    )

                page_texts.append(page_text)

    except pymupdf.EmptyFileError:
        raise

    except pymupdf.FileDataError:
        raise

    full_text = "\n\n".join(
        page_text
        for page_text in page_texts
        if page_text
    )

    if not full_text.strip():
        raise RuntimeError(
            "No extractable text was found. "
            "The PDF may contain scanned images "
            "and may require OCR."
        )

    output_sections: list[str] = []

    for page_number, page_text in enumerate(
        page_texts,
        start=1,
    ):
        output_sections.append(
            f"===== PAGE {page_number} =====\n"
            f"{page_text}"
        )

    output_content = (
        "\n\n"
        .join(output_sections)
        .rstrip()
        + "\n"
    )

    return PDFExtractionResult(
        pdf_path=resolved_path,
        text=output_content,
        page_count=page_count,
        character_count=len(full_text),
        word_count=count_words(full_text),
        pages_without_text=(
            pages_without_text
        ),
    )


def save_extracted_text(
    extraction_result: PDFExtractionResult,
    output_path: Path,
) -> Path:
    resolved_output_path = (
        output_path.expanduser().resolve()
    )

    resolved_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        resolved_output_path.write_text(
            extraction_result.text,
            encoding="utf-8",
        )

    except OSError as exc:
        raise OSError(
            "Could not write the output file: "
            f"{resolved_output_path}"
        ) from exc

    return resolved_output_path


def extract_and_save_pdf_text(
    pdf_path: Path,
    output_path: Path,
) -> tuple[PDFExtractionResult, Path]:
    extraction_result = (
        extract_text_from_pdf(pdf_path)
    )

    saved_path = save_extracted_text(
        extraction_result=extraction_result,
        output_path=output_path,
    )

    return extraction_result, saved_path