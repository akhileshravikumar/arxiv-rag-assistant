from app.services.ingestion_service import (
    IngestionService,
)


def test_normalize_plain_arxiv_id():
    result = IngestionService.normalize_arxiv_id(
        "2005.11401"
    )

    assert result == "2005.11401"


def test_normalize_arxiv_abs_url():
    result = IngestionService.normalize_arxiv_id(
        "https://arxiv.org/abs/2005.11401"
    )

    assert result == "2005.11401"


def test_normalize_pdf_url():
    result = IngestionService.normalize_arxiv_id(
        "https://arxiv.org/pdf/2005.11401.pdf"
    )

    assert result == "2005.11401"