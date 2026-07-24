import os

from celery import Celery
from dotenv import load_dotenv


load_dotenv()


broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "redis://localhost:6379/0",
)

result_backend = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/1",
)


celery_app = Celery(
    "arxiv_research_assistant",
    broker=broker_url,
    backend=result_backend,
    include=[
        "app.tasks.ingestion_tasks",
    ],
)


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    timezone="UTC",
    enable_utc=True,

    task_track_started=True,
    task_send_sent_event=True,

    result_expires=86_400,

    task_time_limit=int(
        os.getenv(
            "CELERY_TASK_TIME_LIMIT",
            "1800",
        )
    ),
    task_soft_time_limit=int(
        os.getenv(
            "CELERY_TASK_SOFT_TIME_LIMIT",
            "1500",
        )
    ),

    worker_prefetch_multiplier=1,

    task_acks_late=True,
    task_reject_on_worker_lost=True,

    broker_connection_retry_on_startup=True,
)