import pytest
from pydantic import ValidationError

from app.schemas.ingestion import ArxivIngestionRequest


def test_valid_arxiv_ids():
    request = ArxivIngestionRequest(
        arxiv_ids=["2005.11401", "1706.03762"]
    )

    assert len(request.arxiv_ids) == 2


def test_empty_list_is_rejected():
    with pytest.raises(ValidationError):
        ArxivIngestionRequest(arxiv_ids=[])


def test_more_than_five_papers_is_rejected():
    with pytest.raises(ValidationError):
        ArxivIngestionRequest(
            arxiv_ids=[
                f"2005.1140{index}"
                for index in range(6)
            ]
        )
