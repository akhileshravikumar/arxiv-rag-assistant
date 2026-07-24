from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import Paper
from app.services.arxiv_service import (
    download_arxiv_paper,
    fetch_arxiv_paper,
    normalize_arxiv_id,
    parse_arxiv_published_date,
)
from app.services.chunking_service import (
    ChunkingService,
    save_chunks_to_database,
)
from app.services.embedding_service import EmbeddingService
from app.services.pdf_service import extract_text_from_pdf


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

RAW_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
)


ProgressCallback = Callable[..., None]


@dataclass(frozen=True)
class IngestionResult:
    paper_id: int
    arxiv_id: str
    title: str
    pdf_path: str
    page_count: int
    character_count: int
    word_count: int
    chunk_count: int
    embedded_chunk_count: int
    duplicate: bool


class DuplicatePaperError(Exception):
    """Raised when a paper already exists in PostgreSQL."""


class IngestionService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        chunking_service: ChunkingService | None = None,
    ) -> None:
        self.embedding_service = embedding_service

        self.chunking_service = (
            chunking_service
            or ChunkingService(
                chunk_size=1000,
                overlap=200,
            )
        )

    @staticmethod
    def normalize_arxiv_id(
        arxiv_id: str,
    ) -> str:
        return normalize_arxiv_id(arxiv_id)

    @staticmethod
    def _base_arxiv_id(
        arxiv_id: str,
    ) -> str:
        """
        Remove the optional arXiv version suffix.

        Example:
        2005.11401v4 -> 2005.11401
        """
        normalized_id = normalize_arxiv_id(
            arxiv_id
        )

        if "v" in normalized_id:
            possible_base, possible_version = (
                normalized_id.rsplit(
                    "v",
                    maxsplit=1,
                )
            )

            if possible_version.isdigit():
                return possible_base

        return normalized_id

    @classmethod
    def _possible_pdf_urls(
        cls,
        arxiv_id: str,
    ) -> set[str]:
        """
        Produce common URL forms that may already be stored.
        """
        normalized_id = normalize_arxiv_id(
            arxiv_id
        )
        base_id = cls._base_arxiv_id(
            normalized_id
        )

        ids = {
            normalized_id,
            base_id,
        }

        urls: set[str] = set()

        for paper_id in ids:
            urls.update(
                {
                    (
                        "https://arxiv.org/pdf/"
                        f"{paper_id}"
                    ),
                    (
                        "https://arxiv.org/pdf/"
                        f"{paper_id}.pdf"
                    ),
                    (
                        "http://arxiv.org/pdf/"
                        f"{paper_id}"
                    ),
                    (
                        "http://arxiv.org/pdf/"
                        f"{paper_id}.pdf"
                    ),
                }
            )

        return urls

    def find_existing_paper(
        self,
        db: Session,
        arxiv_id: str,
        metadata_pdf_url: str | None = None,
    ) -> Paper | None:
        possible_urls = self._possible_pdf_urls(
            arxiv_id
        )

        if metadata_pdf_url:
            possible_urls.add(
                metadata_pdf_url
            )
            possible_urls.add(
                metadata_pdf_url.removesuffix(
                    ".pdf"
                )
            )
            possible_urls.add(
                (
                    metadata_pdf_url
                    if metadata_pdf_url.endswith(
                        ".pdf"
                    )
                    else f"{metadata_pdf_url}.pdf"
                )
            )

        statement = select(Paper).where(
            or_(
                *[
                    Paper.pdf_url == pdf_url
                    for pdf_url in possible_urls
                ]
            )
        )

        return db.scalar(statement)

    @staticmethod
    def _report_progress(
        progress_callback: ProgressCallback | None,
        *,
        stage: str,
        progress: int,
    ) -> None:
        if progress_callback is not None:
            progress_callback(
                stage=stage,
                progress=progress,
            )

    def download_paper(
        self,
        arxiv_id: str,
    ) -> tuple[dict, Path]:
        """
        Fetch metadata for one arXiv paper and download its PDF.
        """
        metadata = fetch_arxiv_paper(
            arxiv_id
        )

        processed_metadata = (
            download_arxiv_paper(
                paper=metadata,
                raw_data_directory=RAW_DATA_DIR,
            )
        )

        download_status = (
            processed_metadata.get(
                "download_status"
            )
        )

        if download_status not in {
            "downloaded",
            "already_exists",
        }:
            error_message = (
                processed_metadata.get(
                    "download_error"
                )
                or (
                    "The paper PDF could not "
                    "be downloaded."
                )
            )

            raise RuntimeError(error_message)

        local_pdf_path = (
            processed_metadata.get(
                "local_pdf_path"
            )
        )

        if not local_pdf_path:
            raise RuntimeError(
                "The downloader did not return "
                "a local PDF path."
            )

        pdf_path = Path(
            local_pdf_path
        ).expanduser().resolve()

        if not pdf_path.exists():
            raise FileNotFoundError(
                f"Downloaded PDF does not exist: "
                f"{pdf_path}"
            )

        return processed_metadata, pdf_path

    @staticmethod
    def create_paper_record(
        db: Session,
        metadata: dict,
    ) -> Paper:
        """
        Add a paper record without committing.

        db.flush() generates paper.id while preserving the
        complete ingestion operation as one transaction.
        """
        title = metadata.get(
            "title",
            "",
        ).strip()

        authors = metadata.get(
            "authors"
        )

        published = metadata.get(
            "published"
        )

        pdf_url = metadata.get(
            "pdf_url"
        )

        if not title:
            raise ValueError(
                "Paper title is missing."
            )

        if not isinstance(authors, list):
            raise ValueError(
                "Paper authors must be a list."
            )

        if not authors:
            raise ValueError(
                "Paper authors are missing."
            )

        if not published:
            raise ValueError(
                "Paper publication date is missing."
            )

        if not pdf_url:
            raise ValueError(
                "Paper PDF URL is missing."
            )

        paper = Paper(
            title=title,
            authors=authors,
            published=(
                parse_arxiv_published_date(
                    published
                )
            ),
            pdf_url=pdf_url,
        )

        db.add(paper)
        db.flush()

        return paper

    def create_chunks(
        self,
        db: Session,
        paper_id: int,
        paper_name: str,
        text: str,
    ) -> list[Chunk]:
        """
        Create overlapping chunks and add them to PostgreSQL
        without committing.
        """
        generated_chunks = (
            self.chunking_service.create_chunks(
                text=text,
                paper_name=paper_name,
            )
        )

        if not generated_chunks:
            raise RuntimeError(
                "No chunks were generated."
            )

        database_result = (
            save_chunks_to_database(
                db=db,
                chunks=generated_chunks,
                paper_id=paper_id,
                replace_existing=False,
                commit=False,
            )
        )

        database_chunks = (
            database_result[
                "database_chunks"
            ]
        )

        if not database_chunks:
            raise RuntimeError(
                "No new database chunks were created."
            )

        return database_chunks

    def generate_embeddings(
        self,
        chunks: list[Chunk],
        batch_size: int = 8,
    ) -> list[list[float]]:
        """
        Generate and attach one vector to every chunk.
        """
        if not chunks:
            raise ValueError(
                "No chunks were supplied for embedding."
            )

        texts = [
            chunk.text
            for chunk in chunks
        ]

        embeddings = (
            self.embedding_service
            .embed_documents(
                texts=texts,
                batch_size=batch_size,
            )
        )

        if len(embeddings) != len(chunks):
            raise RuntimeError(
                "Chunk and embedding counts differ."
            )

        for chunk, embedding in zip(
            chunks,
            embeddings,
            strict=True,
        ):
            chunk.embedding = embedding

        return embeddings

    def ingest(
        self,
        db: Session,
        arxiv_id: str,
        progress_callback: (
            ProgressCallback | None
        ) = None,
    ) -> IngestionResult:
        """
        Run one complete arXiv ingestion operation.

        Database changes are committed only after:
        - metadata is validated;
        - text is extracted;
        - chunks are created;
        - every chunk has an embedding.
        """
        normalized_id = (
            self.normalize_arxiv_id(
                arxiv_id
            )
        )

        self._report_progress(
            progress_callback,
            stage="checking_duplicate",
            progress=5,
        )

        existing_paper = (
            self.find_existing_paper(
                db=db,
                arxiv_id=normalized_id,
            )
        )

        if existing_paper is not None:
            raise DuplicatePaperError(
                f"Paper {normalized_id} is "
                "already ingested with database "
                f"ID {existing_paper.id}."
            )

        self._report_progress(
            progress_callback,
            stage="downloading",
            progress=10,
        )

        metadata, pdf_path = (
            self.download_paper(
                normalized_id
            )
        )

        returned_arxiv_id = (
            metadata.get("arxiv_id")
            or normalized_id
        )

        existing_paper = (
            self.find_existing_paper(
                db=db,
                arxiv_id=returned_arxiv_id,
                metadata_pdf_url=(
                    metadata.get(
                        "pdf_url"
                    )
                ),
            )
        )

        if existing_paper is not None:
            raise DuplicatePaperError(
                f"Paper {returned_arxiv_id} is "
                "already ingested with database "
                f"ID {existing_paper.id}."
            )

        self._report_progress(
            progress_callback,
            stage="extracting_text",
            progress=30,
        )

        extraction_result = (
            extract_text_from_pdf(
                pdf_path
            )
        )

        extracted_text = (
            extraction_result.text
        )

        if not extracted_text.strip():
            raise RuntimeError(
                "PDF text extraction returned "
                "empty text."
            )

        paper: Paper | None = None
        chunks: list[Chunk] = []
        embeddings: list[list[float]] = []

        try:
            self._report_progress(
                progress_callback,
                stage="creating_paper",
                progress=45,
            )

            paper = (
                self.create_paper_record(
                    db=db,
                    metadata=metadata,
                )
            )

            self._report_progress(
                progress_callback,
                stage="chunking",
                progress=55,
            )

            chunks = self.create_chunks(
                db=db,
                paper_id=paper.id,
                paper_name=(
                    metadata.get(
                        "arxiv_id"
                    )
                    or pdf_path.stem
                ),
                text=extracted_text,
            )

            self._report_progress(
                progress_callback,
                stage="embedding",
                progress=70,
            )

            embeddings = (
                self.generate_embeddings(
                    chunks=chunks,
                    batch_size=8,
                )
            )

            self._report_progress(
                progress_callback,
                stage="saving",
                progress=95,
            )

            db.commit()
            db.refresh(paper)

        except Exception:
            db.rollback()
            raise

        self._report_progress(
            progress_callback,
            stage="completed",
            progress=100,
        )

        return IngestionResult(
            paper_id=paper.id,
            arxiv_id=(
                metadata.get(
                    "arxiv_id"
                )
                or normalized_id
            ),
            title=paper.title,
            pdf_path=str(pdf_path),
            page_count=(
                extraction_result.page_count
            ),
            character_count=(
                extraction_result.character_count
            ),
            word_count=(
                extraction_result.word_count
            ),
            chunk_count=len(chunks),
            embedded_chunk_count=len(
                embeddings
            ),
            duplicate=False,
        )