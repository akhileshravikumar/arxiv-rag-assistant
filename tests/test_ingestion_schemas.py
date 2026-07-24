import pytest
from pydantic import ValidationError

from app.schemas.ingestion import IngestionRequest


def test_valid_arxiv_id():
    request = IngestionRequest(
        arxiv_id="2005.11401"
    )

    assert request.arxiv_id == "2005.11401"


def test_empty_arxiv_id_is_rejected():
    with pytest.raises(ValidationError):
        IngestionRequest(arxiv_id="")