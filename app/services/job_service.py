import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

from app.services.redis_service import RedisService


load_dotenv()

logger = logging.getLogger(__name__)


JOB_TTL_SECONDS = int(
    os.getenv(
        "JOB_TTL_SECONDS",
        "3600",
    )
)

# A running job writes a heartbeat at every stage. If one goes quiet for
# longer than this, the instance almost certainly restarted mid-run --
# the known cost of having no worker process on a free tier.
JOB_STALE_AFTER_SECONDS = int(
    os.getenv(
        "JOB_STALE_AFTER_SECONDS",
        "300",
    )
)


JOB_STATE_QUEUED = "queued"
JOB_STATE_RUNNING = "running"
JOB_STATE_COMPLETED = "completed"
JOB_STATE_FAILED = "failed"
JOB_STATE_STALE = "stale"

ACTIVE_JOB_STATES = {
    JOB_STATE_QUEUED,
    JOB_STATE_RUNNING,
}


class JobService:
    def __init__(
        self,
        redis_service: RedisService,
        key_prefix: str = "arxiv-rag:job",
    ) -> None:
        self.redis_service = redis_service
        self.key_prefix = key_prefix

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _key(self, job_id: str) -> str:
        return f"{self.key_prefix}:{job_id}"

    def create(
        self,
        *,
        session_id: str,
        labels: list[str],
    ) -> dict[str, Any]:
        job = {
            "job_id": uuid.uuid4().hex,
            "session_id": session_id,
            "state": JOB_STATE_QUEUED,
            "overall_progress": 0,
            "created_at": self._now().isoformat(),
            "updated_at": self._now().isoformat(),
            "error": None,
            "papers": [
                {
                    "label": label,
                    "stage": "queued",
                    "progress": 0,
                    "paper_id": None,
                    "title": None,
                    "error": None,
                }
                for label in labels
            ],
        }

        self._write(job)

        return job

    def _write(
        self,
        job: dict[str, Any],
    ) -> None:
        job["updated_at"] = (
            self._now().isoformat()
        )

        written = self.redis_service.set_json(
            key=self._key(job["job_id"]),
            value=job,
            ttl_seconds=JOB_TTL_SECONDS,
        )

        if not written:
            # Ingestion itself continues; only the progress report is
            # lost. If writes keep failing the heartbeat stops advancing
            # and the job is reported stale, which is accurate.
            logger.warning(
                "Could not persist job progress",
                extra={
                    "event": "job_write_failed",
                    "job_id": job["job_id"],
                },
            )

    def get(
        self,
        job_id: str,
    ) -> dict[str, Any] | None:
        job = self.redis_service.get_json_strict(
            self._key(job_id)
        )

        if not isinstance(job, dict):
            return None

        if job.get("state") in ACTIVE_JOB_STATES:
            job = self._mark_stale_if_silent(job)

        return job

    def _mark_stale_if_silent(
        self,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            updated_at = datetime.fromisoformat(
                job["updated_at"]
            )

        except (KeyError, ValueError):
            return job

        cutoff = self._now() - timedelta(
            seconds=JOB_STALE_AFTER_SECONDS
        )

        if updated_at >= cutoff:
            return job

        job["state"] = JOB_STATE_STALE
        job["error"] = (
            "The server restarted while this job was "
            "running. Please try again."
        )

        self._write(job)

        return job

    def start(
        self,
        job: dict[str, Any],
    ) -> dict[str, Any]:
        job["state"] = JOB_STATE_RUNNING

        self._write(job)

        return job

    def update_paper(
        self,
        job: dict[str, Any],
        index: int,
        *,
        stage: str,
        progress: int,
        title: str | None = None,
        paper_id: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        papers = job["papers"]

        if index < 0 or index >= len(papers):
            return job

        papers[index]["stage"] = stage
        papers[index]["progress"] = progress

        if title is not None:
            papers[index]["title"] = title

        if paper_id is not None:
            papers[index]["paper_id"] = paper_id

        if error is not None:
            papers[index]["error"] = error

        job["overall_progress"] = round(
            sum(
                paper["progress"]
                for paper in papers
            )
            / max(len(papers), 1)
        )

        self._write(job)

        return job

    def finish(
        self,
        job: dict[str, Any],
        *,
        error: str | None = None,
    ) -> dict[str, Any]:
        succeeded = any(
            paper["paper_id"] is not None
            for paper in job["papers"]
        )

        if error is not None:
            job["state"] = JOB_STATE_FAILED
            job["error"] = error

        elif succeeded:
            job["state"] = JOB_STATE_COMPLETED
            job["overall_progress"] = 100

        else:
            job["state"] = JOB_STATE_FAILED
            job["error"] = (
                "No papers could be added."
            )

        self._write(job)

        return job
