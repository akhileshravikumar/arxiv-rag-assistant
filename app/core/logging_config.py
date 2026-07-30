import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from app.core.request_context import (
    get_request_id,
    get_user_id,
)


load_dotenv()


STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonLogFormatter(logging.Formatter):
    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "user_id": get_user_id(),
        }

        for key, value in record.__dict__.items():
            if (
                key not in STANDARD_LOG_RECORD_FIELDS
                and key not in log_data
                and not key.startswith("_")
            ):
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = (
                self.formatException(
                    record.exc_info
                )
            )

        return json.dumps(
            log_data,
            ensure_ascii=False,
            default=str,
        )


def configure_logging() -> None:
    log_level_name = os.getenv(
        "LOG_LEVEL",
        "INFO",
    ).upper()

    log_level = getattr(
        logging,
        log_level_name,
        logging.INFO,
    )

    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.setFormatter(
        JsonLogFormatter()
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Avoid duplicated access logs from Uvicorn.
    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        logger = logging.getLogger(
            logger_name
        )

        logger.handlers.clear()
        logger.propagate = True