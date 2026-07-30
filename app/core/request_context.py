from contextvars import ContextVar
from typing import Any


request_id_context: ContextVar[str | None] = (
    ContextVar(
        "request_id",
        default=None,
    )
)

user_id_context: ContextVar[int | None] = (
    ContextVar(
        "user_id",
        default=None,
    )
)


def get_request_id() -> str | None:
    return request_id_context.get()


def get_user_id() -> int | None:
    return user_id_context.get()


def set_user_context(
    user_id: int | None,
) -> Any:
    return user_id_context.set(user_id)


def reset_user_context(
    token: Any,
) -> None:
    user_id_context.reset(token)