import argparse
import sys
from pathlib import Path

import pymupdf

from app.services.pdf_service import (
    extract_and_save_pdf_text,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXTRACTED_TEXT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "extracted_text"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract plain text from a PDF "
            "using PyMuPDF."
        )
    )

    parser.add_argument(
        "pdf_path",
        help="Path to the PDF to process.",
    )

    parser.add_argument(
        "--output",
        help=(
            "Optional output text-file path. "
            "Defaults to data/processed/"
            "extracted_text."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    pdf_path = Path(
        arguments.pdf_path
    ).expanduser().resolve()

    if arguments.output:
        output_path = Path(
            arguments.output
        ).expanduser().resolve()
    else:
        output_path = (
            EXTRACTED_TEXT_DIR
            / f"{pdf_path.stem}.txt"
        )

    try:
        extraction_result, saved_path = (
            extract_and_save_pdf_text(
                pdf_path=pdf_path,
                output_path=output_path,
            )
        )

    except FileNotFoundError as exc:
        print(
            f"File error: {exc}",
            file=sys.stderr,
        )
        return 1

    except pymupdf.EmptyFileError as exc:
        print(
            f"PDF error: The PDF is empty. "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    except pymupdf.FileDataError as exc:
        print(
            "PDF error: The file is damaged "
            f"or invalid. {exc}",
            file=sys.stderr,
        )
        return 1

    except PermissionError as exc:
        print(
            f"Permission error: {exc}",
            file=sys.stderr,
        )
        return 1

    except (
        ValueError,
        RuntimeError,
        OSError,
    ) as exc:
        print(
            f"Extraction error: {exc}",
            file=sys.stderr,
        )
        return 1

    print()
    print(
        "PDF text extraction completed "
        "successfully."
    )
    print(
        f"Input PDF: "
        f"{extraction_result.pdf_path}"
    )
    print(f"Output file: {saved_path}")
    print(
        f"Pages: "
        f"{extraction_result.page_count}"
    )
    print(
        "Characters: "
        f"{extraction_result.character_count}"
    )
    print(
        f"Words: "
        f"{extraction_result.word_count}"
    )

    if extraction_result.pages_without_text:
        page_numbers = ", ".join(
            str(page_number)
            for page_number
            in extraction_result.pages_without_text
        )

        print(
            "Pages without extracted text: "
            f"{page_numbers}"
        )
    else:
        print(
            "Pages without extracted text: None"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())