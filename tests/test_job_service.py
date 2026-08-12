import json
from datetime import datetime, timedelta, timezone

from app.services.job_service import (
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_RUNNING,
    JOB_STATE_STALE,
    JobService,
)


class FakeRedisService:
    def __init__(self):
        self.store: dict[str, str] = {}

    def set_json(self, key, value, ttl_seconds):
        self.store[key] = json.dumps(value)

        return True

    def get_json(self, key):
        raw = self.store.get(key)

        return (
            json.loads(raw)
            if raw is not None
            else None
        )


def build_service() -> JobService:
    return JobService(
        redis_service=FakeRedisService()
    )


def test_new_job_starts_queued_with_one_entry_per_paper():
    service = build_service()

    job = service.create(
        session_id="session-a",
        labels=["2005.11401", "paper.pdf"],
    )

    assert job["state"] == "queued"
    assert len(job["papers"]) == 2
    assert job["overall_progress"] == 0


def test_overall_progress_averages_paper_progress():
    service = build_service()

    job = service.create(
        session_id="session-a",
        labels=["a", "b"],
    )

    service.start(job)
    assert job["state"] == JOB_STATE_RUNNING

    service.update_paper(
        job,
        0,
        stage="embedding",
        progress=80,
    )

    assert job["overall_progress"] == 40


def test_job_completes_when_any_paper_succeeds():
    service = build_service()

    job = service.create(
        session_id="session-a",
        labels=["a", "b"],
    )

    service.update_paper(
        job,
        0,
        stage="completed",
        progress=100,
        paper_id=1,
    )

    service.update_paper(
        job,
        1,
        stage="failed",
        progress=100,
        error="broken",
    )

    service.finish(job)

    assert job["state"] == JOB_STATE_COMPLETED
    assert job["overall_progress"] == 100


def test_job_fails_when_no_paper_succeeds():
    service = build_service()

    job = service.create(
        session_id="session-a",
        labels=["a"],
    )

    service.update_paper(
        job,
        0,
        stage="failed",
        progress=100,
        error="broken",
    )

    service.finish(job)

    assert job["state"] == JOB_STATE_FAILED


def test_silent_running_job_is_reported_as_stale():
    service = build_service()

    job = service.create(
        session_id="session-a",
        labels=["a"],
    )

    service.start(job)

    # Simulate the instance restarting mid-run: the heartbeat stops.
    stale_time = (
        datetime.now(timezone.utc)
        - timedelta(hours=1)
    ).isoformat()

    stored = service.redis_service.get_json(
        service._key(job["job_id"])
    )
    stored["updated_at"] = stale_time

    service.redis_service.set_json(
        service._key(job["job_id"]),
        stored,
        60,
    )

    result = service.get(job["job_id"])

    assert result["state"] == JOB_STATE_STALE
    assert result["error"]


def test_unknown_job_returns_none():
    assert build_service().get("nope") is None
