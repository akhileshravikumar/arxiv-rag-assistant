from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from app.core.celery_app import celery_app
from app.dependencies.auth import AdminUser
from app.dependencies.rate_limit import RateLimitedAdminUser
from app.schemas.ingestion import (
    IngestionRequest,
    IngestionSubmissionResponse,
    TaskStatusResponse,
)
from app.tasks.ingestion_tasks import (
    ingest_arxiv_paper_task,
)


router = APIRouter(
    prefix="/ingestion",
    tags=["Ingestion"],
)


@router.post(
    "/arxiv",
    response_model=IngestionSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_arxiv_ingestion(
    request: IngestionRequest,
    admin_user: RateLimitedAdminUser,
):
    task = ingest_arxiv_paper_task.delay(
        arxiv_id=request.arxiv_id,
        requested_by_user_id=admin_user.id,
    )

    return {
        "task_id": task.id,
        "status": "submitted",
        "status_url": (
            f"/ingestion/tasks/{task.id}"
        ),
        "message": (
            "Paper ingestion was submitted "
            "for background processing."
        ),
    }


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
)
def get_ingestion_task_status(
    task_id: str,
    admin_user: AdminUser,
):
    task_result = AsyncResult(
        task_id,
        app=celery_app,
    )

    state = task_result.state
    info = task_result.info

    response = {
        "task_id": task_id,
        "state": state,
        "ready": task_result.ready(),
        "successful": (
            task_result.successful()
            if task_result.ready()
            else None
        ),
        "progress": None,
        "stage": None,
        "result": None,
        "error": None,
    }

    if state == "PROGRESS" and isinstance(
        info,
        dict,
    ):
        response["progress"] = info.get(
            "progress"
        )
        response["stage"] = info.get(
            "stage"
        )

    elif state == "SUCCESS":
        response["progress"] = 100
        response["stage"] = "completed"

        if isinstance(task_result.result, dict):
            response["result"] = (
                task_result.result
            )

    elif state == "FAILURE":
        response["stage"] = "failed"
        response["error"] = str(
            task_result.result
        )

    elif state == "RETRY":
        response["stage"] = "retrying"
        response["error"] = str(info)

    elif state == "STARTED":
        response["stage"] = "started"
        response["progress"] = 0

    elif state == "PENDING":
        response["stage"] = "queued"
        response["progress"] = 0

    return response