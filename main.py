import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.container import build_container
from app.core.exception_handlers import (
    register_exception_handlers,
)
from app.core.logging_config import configure_logging
from app.database.database import (
    Base,
    get_engine,
    get_session_factory,
)
from app.middleware.request_logging import (
    RequestLoggingMiddleware,
)
from app.routers.chat import router as chat_router
from app.routers.ingestion import (
    router as ingestion_router,
)
from app.routers.search import router as search_router
from app.routers.sessions import (
    router as sessions_router,
)
from app.services.redis_service import redis_service
from app.services.session_service import SessionService


load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)


def allowed_origins() -> list[str]:
    configured = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000",
    )

    return [
        origin.strip()
        for origin in configured.split(",")
        if origin.strip()
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    Base.metadata.create_all(bind=engine)

    app.state.services = build_container()

    logger.info(
        "Application started",
        extra={"event": "application_started"},
    )

    yield


app = FastAPI(
    title="ArXiv RAG Assistant API",
    description=(
        "Ephemeral, session-scoped retrieval-augmented "
        "search over arXiv papers and uploaded PDFs."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "Retry-After",
    ],
)

app.add_middleware(RequestLoggingMiddleware)

register_exception_handlers(app)

app.include_router(sessions_router)
app.include_router(ingestion_router)
app.include_router(chat_router)
app.include_router(search_router)


@app.get(
    "/",
    tags=["General"],
    summary="API welcome endpoint",
)
def read_root():
    return {
        "message": (
            "Welcome to the ArXiv RAG Assistant API"
        ),
        "docs": "/docs",
    }


@app.get(
    "/health",
    tags=["System"],
)
def health_check():
    database_healthy = False
    expired_removed = 0

    try:
        with get_session_factory()() as db:
            db.execute(text("SELECT 1"))

            # Free tiers have no scheduler, so the keep-alive ping
            # doubles as the cleanup trigger for expired sessions.
            expired_removed = (
                SessionService().purge_expired(db)
            )

        database_healthy = True

    except Exception:
        logger.exception(
            "Database health check failed",
            extra={
                "event": "database_health_failed"
            },
        )

    redis_healthy = redis_service.ping()

    return {
        "status": (
            "healthy"
            if database_healthy and redis_healthy
            else "degraded"
        ),
        "database": (
            "connected"
            if database_healthy
            else "unavailable"
        ),
        "redis": (
            "connected"
            if redis_healthy
            else "unavailable"
        ),
        "expired_sessions_removed": (
            expired_removed
        ),
    }


@app.get(
    "/ready",
    tags=["System"],
)
def readiness_check():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

        database_ready = True

    except Exception:
        database_ready = False

    redis_ready = redis_service.ping()

    if not (database_ready and redis_ready):
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Application is not ready.",
        )

    return {
        "status": "ready",
        "database": "connected",
        "redis": "connected",
    }
