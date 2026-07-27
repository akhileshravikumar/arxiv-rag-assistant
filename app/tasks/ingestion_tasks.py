import os

from celery import states
from celery.exceptions import (
    MaxRetriesExceededError,
    SoftTimeLimitExceeded,
)
from sqlalchemy.exc import (
    OperationalError,
    SQLAlchemyError,
)

from app.core.celery_app import celery_app
from app.database.database import SessionLocal
from app.services.embedding_service import (
    EmbeddingService,
)
from app.services.ingestion_service import (
    DuplicatePaperError,
    IngestionService,
)
from app.services.redis_service import redis_service
from app.services.cache_key_service import (
    CacheKeyService,
)
from app.services.cache_service import (
    CacheService,
)

MAX_RETRIES = int(
    os.getenv(
        "INGESTION_MAX_RETRIES",
        "3",
    )
)

LOCK_TTL_SECONDS = int(
    os.getenv(
        "INGESTION_LOCK_TTL_SECONDS",
        "3600",
    )
)


@celery_app.task(
    bind=True,
    name="papers.ingest_arxiv_paper",
    max_retries=MAX_RETRIES,
)
def ingest_arxiv_paper_task(
    self,
    arxiv_id: str,
    requested_by_user_id: int,
) -> dict:
    task_id = self.request.id
    normalized_id = (
        IngestionService.normalize_arxiv_id(
            arxiv_id
        )
    )

    lock_key = (
        f"ingestion:paper:{normalized_id}"
    )

    lock_acquired = redis_service.acquire_lock(
        key=lock_key,
        value=task_id,
        ttl_seconds=LOCK_TTL_SECONDS,
    )

    if not lock_acquired:
        return {
            "status": "duplicate",
            "message": (
                "Another ingestion task is already "
                "processing this paper."
            ),
            "arxiv_id": normalized_id,
        }

    db = SessionLocal()

    def report_progress(
        stage: str,
        progress: int,
    ) -> None:
        self.update_state(
            state="PROGRESS",
            meta={
                "stage": stage,
                "progress": progress,
                "arxiv_id": normalized_id,
            },
        )

    try:
        report_progress(
            stage="starting",
            progress=5,
        )

        embedding_service = EmbeddingService()
        cache_service = CacheService(
            redis_service=redis_service,    
            key_service=CacheKeyService(),
        )
        ingestion_service = IngestionService(
            embedding_service=embedding_service
        )

        result = ingestion_service.ingest(
            db=db,
            arxiv_id=normalized_id,
            progress_callback=report_progress,
        )

        new_corpus_version = (
            cache_service.increment_corpus_version()
        )

        return {
            "status": "completed",
            "paper_id": result.paper_id,
            "arxiv_id": result.arxiv_id,
            "title": result.title,
            "pdf_path": result.pdf_path,
            "page_count": result.page_count,
            "character_count": result.character_count,
            "word_count": result.word_count,
            "chunk_count": result.chunk_count,
            "embedded_chunk_count": (
                result.embedded_chunk_count
            ),
            "corpus_version": new_corpus_version,
            "requested_by_user_id": (
                requested_by_user_id
            ),
        }

    except DuplicatePaperError as exc:
        db.rollback()

        return {
            "status": "duplicate",
            "arxiv_id": normalized_id,
            "message": str(exc),
        }

    except (
        OperationalError,
        ConnectionError,
        TimeoutError,
    ) as exc:
        db.rollback()

        try:
            raise self.retry(
                exc=exc,
                countdown=min(
                    30 * (2 ** self.request.retries),
                    300,
                ),
            )

        except MaxRetriesExceededError:
            raise RuntimeError(
                "Ingestion failed after all retries."
            ) from exc

    except SoftTimeLimitExceeded as exc:
        db.rollback()

        raise RuntimeError(
            "Ingestion exceeded its time limit."
        ) from exc

    except SQLAlchemyError:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

        redis_service.release_lock(
            key=lock_key,
            expected_value=task_id,
        )