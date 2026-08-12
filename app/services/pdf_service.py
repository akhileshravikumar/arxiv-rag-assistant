from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class PDFExtractionResult:
    pdf_path: Path
    # Page-delimited, for inspection and debugging.
    text: str
    # Marker-free, for chunking and embedding.
    plain_text: str
    title: str | None
    authors: list[str]
    page_count: int
    character_count: int
    word_count: int
    pages_without_text: list[int]


MAX_TITLE_LENGTH = 300


def count_words(text: str) -> int:
    return len(text.split())


def derive_title(
    metadata: dict,
    first_page_text: str,
    fallback: str,
) -> str:
    """
    Best-effort title for an uploaded PDF.

    Embedded metadata is preferred, then the first substantial line of
    page one, then the filename. The user can rename the paper
    afterwards, so a wrong guess is cheap.
    """
    embedded_title = (
        metadata.get("title") or ""
    ).strip()

    if len(embedded_title) >= 8:
        return embedded_title[
            :MAX_TITLE_LENGTH
        ]

    for line in first_page_text.splitlines():
        candidate = " ".join(line.split())

        # Skip page furniture, arXiv stamps and section numbers.
        if len(candidate) < 12:
            continue

        if candidate.lower().startswith(
            (
                "arxiv:",
                "preprint",
                "under review",
                "published as",
            )
        ):
            continue

        return candidate[:MAX_TITLE_LENGTH]

    return fallback[:MAX_TITLE_LENGTH]


def derive_authors(
    metadata: dict,
) -> list[str]:
    raw_authors = (
        metadata.get("author") or ""
    ).strip()

    if not raw_authors:
        return ["Unknown"]

    separators = [";", ",", " and "]

    for separator in separators:
        if separator in raw_authors:
            authors = [
                author.strip()
                for author in raw_authors.split(
                    separator
                )
                if author.strip()
            ]

            if authors:
                return authors[:25]

    return [raw_authors]


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
    document_metadata: dict = {}

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

            document_metadata = (
                document.metadata or {}
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
        plain_text=full_text,
        title=derive_title(
            metadata=document_metadata,
            first_page_text=(
                page_texts[0]
                if page_texts
                else ""
            ),
            fallback=resolved_path.stem,
        ),
        authors=derive_authors(
            document_metadata
        ),
        page_count=page_count,
        character_count=len(full_text),
        word_count=count_words(full_text),
        pages_without_text=(
            pages_without_text
        ),
    )


def count_pdf_pages(
    pdf_bytes: bytes,
) -> int:
    """
    Read a page count without extracting text, for upload validation.
    """
    with pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf",
    ) as document:
        if document.needs_pass:
            raise PermissionError(
                "The PDF is password-protected "
                "and cannot be read."
            )

        return document.page_count