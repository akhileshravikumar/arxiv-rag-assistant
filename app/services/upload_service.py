import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from dotenv import load_dotenv

from app.services.pdf_service import count_pdf_pages


load_dotenv()


PDF_MAGIC_BYTES = b"%PDF-"

MAX_UPLOAD_BYTES = int(
    os.getenv(
        "MAX_UPLOAD_BYTES",
        str(15 * 1024 * 1024),
    )
)

MAX_UPLOAD_PAGES = int(
    os.getenv(
        "MAX_UPLOAD_PAGES",
        "80",
    )
)


class InvalidUploadError(Exception):
    """Raised when an uploaded file is not usable as a paper."""


@dataclass(frozen=True)
class SavedUpload:
    original_filename: str
    stored_path: Path
    size_bytes: int
    page_count: int


def sanitize_upload_filename(
    filename: str | None,
) -> str:
    candidate = (filename or "").strip()

    # Defeat directory traversal by keeping the basename only.
    candidate = Path(candidate).name

    candidate = re.sub(
        r"[^A-Za-z0-9._ -]",
        "",
        candidate,
    ).strip()

    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"

    return candidate[:255] or "upload.pdf"


def create_upload_directory() -> Path:
    """
    Uploads live in the system temp directory.

    Free-tier instances have no persistent disk, so nothing about the
    deployment should assume these files survive a restart.
    """
    directory = Path(
        tempfile.mkdtemp(
            prefix="arxiv-rag-upload-"
        )
    )

    return directory


def validate_and_save_upload(
    *,
    filename: str | None,
    content: bytes,
    directory: Path,
) -> SavedUpload:
    safe_filename = sanitize_upload_filename(
        filename
    )

    if not content:
        raise InvalidUploadError(
            f"{safe_filename} is empty."
        )

    if len(content) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (
            1024 * 1024
        )

        raise InvalidUploadError(
            f"{safe_filename} is larger than "
            f"{limit_mb} MB."
        )

    if not content.startswith(PDF_MAGIC_BYTES):
        raise InvalidUploadError(
            f"{safe_filename} is not a PDF file."
        )

    try:
        page_count = count_pdf_pages(content)

    except PermissionError as exc:
        raise InvalidUploadError(
            f"{safe_filename} is password-protected."
        ) from exc

    except (
        pymupdf.FileDataError,
        pymupdf.EmptyFileError,
        RuntimeError,
        ValueError,
    ) as exc:
        raise InvalidUploadError(
            f"{safe_filename} could not be read as a PDF."
        ) from exc

    if page_count < 1:
        raise InvalidUploadError(
            f"{safe_filename} contains no pages."
        )

    if page_count > MAX_UPLOAD_PAGES:
        raise InvalidUploadError(
            f"{safe_filename} has {page_count} pages; "
            f"the limit is {MAX_UPLOAD_PAGES}."
        )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Prefix with a UUID so two uploads with the same name coexist.
    stored_path = (
        directory
        / f"{uuid.uuid4().hex}_{safe_filename}"
    )

    stored_path.write_bytes(content)

    return SavedUpload(
        original_filename=safe_filename,
        stored_path=stored_path,
        size_bytes=len(content),
        page_count=page_count,
    )
