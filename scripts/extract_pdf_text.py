import argparse
import sys
from pathlib import Path

import pymupdf


# Locate the project root regardless of where this script is executed from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "extracted_text"


def count_words(text: str) -> int:
    return len(text.split())


def extract_pdf_text(
    pdf_path: Path,
    output_path: Path,
) -> dict:
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF does not exist: {pdf_path}"
        )

    if not pdf_path.is_file():
        raise ValueError(
            f"The supplied path is not a file: {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"The supplied file is not a PDF: {pdf_path.name}"
        )

    # Create data/processed if it does not already exist.
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_texts: list[str] = []
    pages_without_text: list[int] = []

    # Using a context manager closes the PDF automatically.
    with pymupdf.open(pdf_path) as document:
        if document.needs_pass:
            raise PermissionError(
                "The PDF is password-protected and cannot be read."
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
            # sort=True attempts a top-left to bottom-right reading order.
            page_text = page.get_text(
                "text",
                sort=True,
            ).strip()

            if not page_text:
                pages_without_text.append(page_number)

            page_texts.append(page_text)

    full_text = "\n\n".join(
        page_text
        for page_text in page_texts
        if page_text
    )

    if not full_text.strip():
        raise RuntimeError(
            "No extractable text was found. "
            "The PDF may contain scanned page images and may require OCR."
        )

    character_count = len(full_text)
    word_count = count_words(full_text)

    # Add page markers to make the resulting file easier to inspect
    output_sections: list[str] = []

    for page_number, page_text in enumerate(
        page_texts,
        start=1,
    ):
        section = (
            f"===== PAGE {page_number} =====\n"
            f"{page_text}"
        )

        output_sections.append(section)

    output_content = "\n\n".join(output_sections).rstrip() + "\n"

    try:
        output_path.write_text(
            output_content,
            encoding="utf-8",
        )
    except OSError as exc:
        raise OSError(
            f"Could not write the output file: {output_path}"
        ) from exc

    return {
        "pdf_path": str(pdf_path),
        "output_path": str(output_path),
        "page_count": page_count,
        "character_count": character_count,
        "word_count": word_count,
        "pages_without_text": pages_without_text,
    }


def parse_arguments() -> argparse.Namespace:
    """
    Read the PDF path and optional output path from the terminal.
    """
    parser = argparse.ArgumentParser(
        description="Extract plain text from a PDF using PyMuPDF."
    )

    parser.add_argument(
        "pdf_path",
        help="Path to the PDF that should be processed.",
    )

    parser.add_argument(
        "--output",
        help=(
            "Optional output text-file path. "
            "By default, the file is saved under data/processed."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    pdf_path = Path(arguments.pdf_path).expanduser().resolve()

    if arguments.output:
        output_path = Path(arguments.output).expanduser().resolve()
    else:
        output_path = (
            PROCESSED_DATA_DIR
            / f"{pdf_path.stem}.txt"
        )

    try:
        statistics = extract_pdf_text(
            pdf_path=pdf_path,
            output_path=output_path,
        )

    except FileNotFoundError as exc:
        print(
            f"File error: {exc}",
            file=sys.stderr,
        )
        return 1

    except pymupdf.EmptyFileError as exc:
        print(
            f"PDF error: The PDF is empty. {exc}",
            file=sys.stderr,
        )
        return 1

    except pymupdf.FileDataError as exc:
        print(
            f"PDF error: The file is damaged or is not a valid PDF. {exc}",
            file=sys.stderr,
        )
        return 1

    except PermissionError as exc:
        print(
            f"Permission error: {exc}",
            file=sys.stderr,
        )
        return 1

    except (ValueError, RuntimeError, OSError) as exc:
        print(
            f"Extraction error: {exc}",
            file=sys.stderr,
        )
        return 1

    print()
    print("PDF text extraction completed successfully.")
    print(f"Input PDF: {statistics['pdf_path']}")
    print(f"Output file: {statistics['output_path']}")
    print(f"Pages: {statistics['page_count']}")
    print(f"Characters: {statistics['character_count']}")
    print(f"Words: {statistics['word_count']}")

    pages_without_text = statistics["pages_without_text"]

    if pages_without_text:
        page_numbers = ", ".join(
            str(page_number)
            for page_number in pages_without_text
        )

        print(f"Pages without extracted text: {page_numbers}")
    else:
        print("Pages without extracted text: None")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())