import logging
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.container import ServiceContainer
from app.database.database import (
    get_db,
    get_session_factory,
)
from app.dependencies.rate_limit import (
    limit_ingestion_requests,
)
from app.dependencies.services import Services
from app.models.paper import (
    PAPER_SOURCE_ARXIV,
    PAPER_SOURCE_UPLOAD,
)
from app.models.session import ResearchSession
from app.schemas.ingestion import (
    ArxivIngestionRequest,
    JobStatusResponse,
    JobSubmissionResponse,
)
from app.services.ingestion_service import (
    DuplicatePaperError,
    PendingPaper,
    cleanup_directory,
    create_download_directory,
)
from app.services.redis_service import (
    RedisUnavailableError,
)
from app.services.upload_service import (
    InvalidUploadError,
    create_upload_directory,
    validate_and_save_upload,
)


logger = logging.getLogger(__name__)


router = APIRouter(tags=["Ingestion"])


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]

RateLimitedSession = Annotated[
    ResearchSession,
    Depends(limit_ingestion_requests),
]


def run_ingestion(
    *,
    services: ServiceContainer,
    session_id: str,
    job: dict,
    pending_papers: list[PendingPaper],
    scratch_directories: list[Path],
) -> None:
    """
    Ingest papers in the background.

    Free-tier hosting has no worker process, so this runs inside the web
    instance. It opens its own database session because the request that
    scheduled it has already returned.
    """
    job_service = services.job_service
    ingestion_service = services.ingestion_service

    download_directory = (
        create_download_directory()
    )

    scratch_directories.append(
        download_directory
    )

    job_service.start(job)

    db = get_session_factory()()

    try:
        for index, pending in enumerate(
            pending_papers
        ):

            def report(
                *,
                stage: str,
                progress: int,
                _index: int = index,
            ) -> None:
                job_service.update_paper(
                    job,
                    _index,
                    stage=stage,
                    progress=progress,
                )

            try:
                result = (
                    ingestion_service.ingest_one(
                        db=db,
                        session_id=session_id,
                        pending=pending,
                        download_directory=(
                            download_directory
                        ),
                        progress_callback=report,
                    )
                )

                job_service.update_paper(
                    job,
                    index,
                    stage="completed",
                    progress=100,
                    title=result.title,
                    paper_id=result.paper_id,
                )

            except DuplicatePaperError as exc:
                job_service.update_paper(
                    job,
                    index,
                    stage="skipped",
                    progress=100,
                    error=str(exc),
                )

            except Exception as exc:
                logger.exception(
                    "Paper ingestion failed",
                    extra={
                        "event": "ingestion_failed",
                        "session_id": session_id,
                        "label": pending.label,
                    },
                )

                job_service.update_paper(
                    job,
                    index,
                    stage="failed",
                    progress=100,
                    error=str(exc),
                )

        # The session's corpus changed, so drop the cached lexical
        # index and invalidate any cached answers.
        services.bm25_service.invalidate(
            session_id
        )

        services.cache_service.increment_corpus_version(
            session_id
        )

        job_service.finish(job)

    except Exception as exc:
        logger.exception(
            "Ingestion job failed",
            extra={
                "event": "ingestion_job_failed",
                "session_id": session_id,
            },
        )

        job_service.finish(
            job,
            error=str(exc),
        )

    finally:
        db.close()

        for directory in scratch_directories:
            cleanup_directory(directory)


def check_capacity(
    db: Session,
    services: Services,
    session_id: str,
    requested: int,
) -> None:
    remaining = (
        services.session_service.remaining_paper_slots(
            db,
            session_id,
        )
    )

    if requested > remaining:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                f"This session can hold "
                f"{services.session_service.max_papers} "
                f"papers. {remaining} slot(s) remain."
            ),
        )


def submission_response(
    job: dict,
) -> dict:
    return {
        "job_id": job["job_id"],
        "state": job["state"],
        "status_url": f"/jobs/{job['job_id']}",
        "message": (
            "Ingestion started. Poll the status URL "
            "for progress."
        ),
    }


@router.post(
    "/sessions/{session_id}/ingest/arxiv",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest chosen arXiv papers",
)
def ingest_arxiv_papers(
    request: ArxivIngestionRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    services: Services,
    session: RateLimitedSession,
):
    arxiv_ids = [
        arxiv_id.strip()
        for arxiv_id in request.arxiv_ids
        if arxiv_id.strip()
    ]

    if not arxiv_ids:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail="No arXiv IDs were supplied.",
        )

    check_capacity(
        db=db,
        services=services,
        session_id=session.id,
        requested=len(arxiv_ids),
    )

    pending_papers = [
        PendingPaper(
            label=arxiv_id,
            source=PAPER_SOURCE_ARXIV,
            arxiv_id=arxiv_id,
        )
        for arxiv_id in arxiv_ids
    ]

    job = services.job_service.create(
        session_id=session.id,
        labels=[
            pending.label
            for pending in pending_papers
        ],
    )

    background_tasks.add_task(
        run_ingestion,
        services=services,
        session_id=session.id,
        job=job,
        pending_papers=pending_papers,
        scratch_directories=[],
    )

    return submission_response(job)


@router.post(
    "/sessions/{session_id}/ingest/upload",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest uploaded PDFs",
)
async def ingest_uploaded_papers(
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    services: Services,
    session: RateLimitedSession,
    files: Annotated[
        list[UploadFile],
        File(),
    ],
):
    if not files:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail="No files were uploaded.",
        )

    check_capacity(
        db=db,
        services=services,
        session_id=session.id,
        requested=len(files),
    )

    upload_directory = create_upload_directory()

    pending_papers: list[PendingPaper] = []

    try:
        for upload in files:
            # UploadFile is closed once the response returns, so the
            # bytes must be read here rather than in the background.
            content = await upload.read()

            saved = validate_and_save_upload(
                filename=upload.filename,
                content=content,
                directory=upload_directory,
            )

            pending_papers.append(
                PendingPaper(
                    label=(
                        saved.original_filename
                    ),
                    source=PAPER_SOURCE_UPLOAD,
                    pdf_path=saved.stored_path,
                    filename=(
                        saved.original_filename
                    ),
                )
            )

    except InvalidUploadError as exc:
        cleanup_directory(upload_directory)

        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc

    except Exception:
        cleanup_directory(upload_directory)
        raise

    job = services.job_service.create(
        session_id=session.id,
        labels=[
            pending.label
            for pending in pending_papers
        ],
    )

    background_tasks.add_task(
        run_ingestion,
        services=services,
        session_id=session.id,
        job=job,
        pending_papers=pending_papers,
        scratch_directories=[upload_directory],
    )

    return submission_response(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["Jobs"],
    summary="Poll an ingestion job",
)
def get_job_status(
    job_id: str,
    services: Services,
):
    try:
        job = services.job_service.get(job_id)

    except RedisUnavailableError as exc:
        # Distinct from 404 on purpose: the job may be running fine and
        # the client should keep polling rather than give up.
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The job store is temporarily "
                "unavailable. Retry shortly."
            ),
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "This job is unknown or has expired."
            ),
        )

    return job
