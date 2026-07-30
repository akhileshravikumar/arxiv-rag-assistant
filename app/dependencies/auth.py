from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.services.token_service import TokenService

from app.core.request_context import (
    user_id_context,
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

token_service = TokenService()


def get_current_user(
    token: Annotated[
        str,
        Depends(oauth2_scheme),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials.",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = (
            token_service.decode_access_token(
                token
            )
        )

        user_id = payload.get("user_id")
        email = payload.get("sub")

        if user_id is None or email is None:
            raise credentials_exception

    except ValueError as exc:
        raise credentials_exception from exc

    user = db.scalar(
        select(User).where(
            User.id == int(user_id)
        )
    )

    if user is None:
        raise credentials_exception

    if user.email != email:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    user_id_context.set(user.id)

    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]

def require_admin(
    current_user: CurrentUser,
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return current_user


AdminUser = Annotated[
    User,
    Depends(require_admin),
]