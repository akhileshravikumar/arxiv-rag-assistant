import pytest

from app.services.upload_service import (
    InvalidUploadError,
    sanitize_upload_filename,
    validate_and_save_upload,
)


def save(tmp_path, filename, content):
    return validate_and_save_upload(
        filename=filename,
        content=content,
        directory=tmp_path,
    )


def test_directory_traversal_is_stripped():
    assert (
        sanitize_upload_filename(
            "../../etc/passwd.pdf"
        )
        == "passwd.pdf"
    )


def test_extension_is_enforced():
    assert sanitize_upload_filename(
        "notes"
    ).endswith(".pdf")


def test_missing_filename_gets_a_default():
    assert (
        sanitize_upload_filename(None)
        == "upload.pdf"
    )


def test_name_that_sanitizes_to_nothing_gets_a_default():
    # Every character is stripped, leaving no stem to build on.
    assert (
        sanitize_upload_filename("???.pdf")
        == "upload.pdf"
    )

    assert (
        sanitize_upload_filename("   ")
        == "upload.pdf"
    )


def test_existing_extension_is_not_duplicated():
    assert (
        sanitize_upload_filename("paper.pdf")
        == "paper.pdf"
    )


def test_empty_file_is_rejected(tmp_path):
    with pytest.raises(
        InvalidUploadError,
        match="empty",
    ):
        save(tmp_path, "paper.pdf", b"")


def test_non_pdf_content_is_rejected(tmp_path):
    with pytest.raises(
        InvalidUploadError,
        match="not a PDF",
    ):
        save(
            tmp_path,
            "paper.pdf",
            b"<html>not a pdf</html>",
        )


def test_corrupt_pdf_is_rejected(tmp_path):
    with pytest.raises(
        InvalidUploadError,
        match="could not be read",
    ):
        save(
            tmp_path,
            "paper.pdf",
            b"%PDF-1.4\nbut then garbage",
        )


def test_oversized_file_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.upload_service.MAX_UPLOAD_BYTES",
        16,
    )

    with pytest.raises(
        InvalidUploadError,
        match="larger than",
    ):
        save(
            tmp_path,
            "paper.pdf",
            b"%PDF-" + b"0" * 100,
        )
