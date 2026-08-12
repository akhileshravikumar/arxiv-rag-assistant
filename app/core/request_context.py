from contextvars import ContextVar
from typing import Any


request_id_context: ContextVar[str | None] = (
    ContextVar(
        "request_id",
        default=None,
    )
)

session_id_context: ContextVar[str | None] = (
    ContextVar(
        "session_id",
        default=None,
    )
)


def get_request_id() -> str | None:
    return request_id_context.get()


def get_session_id() -> str | None:
    return session_id_context.get()


def set_session_context(
    session_id: str | None,
) -> Any:
    return session_id_context.set(session_id)


def reset_session_context(
    token: Any,
) -> None:
    session_id_context.reset(token)
