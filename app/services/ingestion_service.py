import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.paper import (
    PAPER_SOURCE_ARXIV,
    PAPER_SOURCE_UPLOAD,
    Paper,
)
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


logger = logging.getLogger(__name__)


class DuplicatePaperError(Exception):
    """Raised when a session already contains this paper."""


@dataclass(frozen=True)
class PendingPaper:
    """
    One paper waiting to be ingested, from either input path.

    arXiv papers carry an identifier and are downloaded by the worker.
    Uploads are already on disk, saved by the request handler before the
    upload stream closed.
    """

    label: str
    source: str
    arxiv_id: str | None = None
    pdf_path: Path | None = None
    filename: str | None = None


@dataclass(frozen=True)
class IngestedPaper:
    paper_id: int
    title: str
    page_count: int
    chunk_count: int


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
    def find_existing_paper(
        db: Session,
        session_id: str,
        *,
        arxiv_id: str | None = None,
        filename: str | None = None,
    ) -> Paper | None:
        """
        Look for a paper already present in this session.
        """
        statement = select(Paper).where(
            Paper.session_id == session_id
        )

        if arxiv_id:
            base_id = arxiv_id.split(
                "v",
                maxsplit=1,
            )[0]

            statement = statement.where(
                Paper.arxiv_id.startswith(base_id)
            )

        elif filename:
            statement = statement.where(
                Paper.filename == filename
            )

        else:
            return None

        return db.scalar(statement)

    def _prepare_arxiv_paper(
        self,
        db: Session,
        session_id: str,
        pending: PendingPaper,
        download_directory: Path,
    ) -> tuple[dict, Path]:
        normalized_id = normalize_arxiv_id(
            pending.arxiv_id or ""
        )

        if self.find_existing_paper(
            db,
            session_id,
            arxiv_id=normalized_id,
        ):
            raise DuplicatePaperError(
                f"{normalized_id} is already in this session."
            )

        metadata = fetch_arxiv_paper(
            normalized_id
        )

        processed = download_arxiv_paper(
            paper=metadata,
            raw_data_directory=download_directory,
        )

        if processed.get(
            "download_status"
        ) not in {
            "downloaded",
            "already_exists",
        }:
            raise RuntimeError(
                processed.get("download_error")
                or "The paper PDF could not be downloaded."
            )

        local_pdf_path = processed.get(
            "local_pdf_path"
        )

        if not local_pdf_path:
            raise RuntimeError(
                "The downloader did not return a local PDF path."
            )

        pdf_path = Path(local_pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(
                f"Downloaded PDF does not exist: {pdf_path}"
            )

        return processed, pdf_path

    @staticmethod
    def _build_paper_record(
        session_id: str,
        pending: PendingPaper,
        metadata: dict | None,
        extraction,
    ) -> Paper:
        if (
            pending.source == PAPER_SOURCE_ARXIV
            and metadata
        ):
            title = (
                metadata.get("title") or ""
            ).strip()

            authors = (
                metadata.get("authors") or []
            )

            published_value = metadata.get(
                "published"
            )

            published: date | None = (
                parse_arxiv_published_date(
                    published_value
                )
                if published_value
                else None
            )

            arxiv_id = metadata.get("arxiv_id")

            pdf_url = (
                f"https://arxiv.org/pdf/{arxiv_id}"
                if arxiv_id
                else metadata.get("pdf_url")
            )

            if not title:
                raise ValueError(
                    "The arXiv record has no title."
                )

            return Paper(
                session_id=session_id,
                title=title,
                authors=authors or ["Unknown"],
                published=published,
                source=PAPER_SOURCE_ARXIV,
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
                filename=None,
                page_count=extraction.page_count,
            )

        return Paper(
            session_id=session_id,
            title=(
                extraction.title
                or pending.label
            ),
            authors=extraction.authors,
            published=None,
            source=PAPER_SOURCE_UPLOAD,
            arxiv_id=None,
            pdf_url=None,
            filename=pending.filename
            or pending.label,
            page_count=extraction.page_count,
        )

    def _create_chunks(
        self,
        db: Session,
        paper_id: int,
        paper_name: str,
        text: str,
    ) -> list[Chunk]:
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

        database_result = save_chunks_to_database(
            db=db,
            chunks=generated_chunks,
            paper_id=paper_id,
            replace_existing=False,
            commit=False,
        )

        database_chunks = database_result[
            "database_chunks"
        ]

        if not database_chunks:
            raise RuntimeError(
                "No new database chunks were created."
            )

        return database_chunks

    def _embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> int:
        if not chunks:
            raise ValueError(
                "No chunks were supplied for embedding."
            )

        embeddings = (
            self.embedding_service.embed_documents(
                texts=[
                    chunk.text
                    for chunk in chunks
                ]
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

        return len(embeddings)

    def ingest_one(
        self,
        db: Session,
        session_id: str,
        pending: PendingPaper,
        download_directory: Path,
        progress_callback=None,
    ) -> IngestedPaper:
        """
        Ingest a single paper inside one database transaction.

        Nothing is committed until the paper record, its chunks and
        every embedding are all in place.
        """

        def report(stage: str, progress: int) -> None:
            if progress_callback is not None:
                progress_callback(
                    stage=stage,
                    progress=progress,
                )

        metadata: dict | None = None

        if pending.source == PAPER_SOURCE_ARXIV:
            report("downloading", 15)

            metadata, pdf_path = (
                self._prepare_arxiv_paper(
                    db=db,
                    session_id=session_id,
                    pending=pending,
                    download_directory=(
                        download_directory
                    ),
                )
            )

        else:
            if pending.pdf_path is None:
                raise RuntimeError(
                    "The uploaded file is missing."
                )

            if self.find_existing_paper(
                db,
                session_id,
                filename=pending.filename,
            ):
                raise DuplicatePaperError(
                    f"{pending.label} is already in this session."
                )

            pdf_path = pending.pdf_path

        report("extracting_text", 35)

        extraction = extract_text_from_pdf(
            pdf_path
        )

        if not extraction.plain_text.strip():
            raise RuntimeError(
                "PDF text extraction returned empty text."
            )

        try:
            report("creating_paper", 50)

            paper = self._build_paper_record(
                session_id=session_id,
                pending=pending,
                metadata=metadata,
                extraction=extraction,
            )

            db.add(paper)
            db.flush()

            report("chunking", 60)

            chunks = self._create_chunks(
                db=db,
                paper_id=paper.id,
                paper_name=(
                    paper.arxiv_id
                    or paper.filename
                    or pdf_path.stem
                ),
                text=extraction.plain_text,
            )

            report("embedding", 80)

            self._embed_chunks(chunks)

            report("saving", 95)

            db.commit()
            db.refresh(paper)

        except Exception:
            db.rollback()
            raise

        report("completed", 100)

        return IngestedPaper(
            paper_id=paper.id,
            title=paper.title,
            page_count=extraction.page_count,
            chunk_count=len(chunks),
        )


def create_download_directory() -> Path:
    """
    Scratch space for arXiv PDFs during one ingestion run.
    """
    return Path(
        tempfile.mkdtemp(
            prefix="arxiv-rag-download-"
        )
    )


def cleanup_directory(
    directory: Path | None,
) -> None:
    if directory is None:
        return

    shutil.rmtree(
        directory,
        ignore_errors=True,
    )
