from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.dependencies.auth import CurrentUser
from app.schemas.auth import (
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.token_service import TokenService


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

token_service = TokenService()

auth_service = AuthService(
    token_service=token_service
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: UserRegisterRequest,
    db: DatabaseSession,
):
    try:
        return auth_service.register_user(
            db=db,
            email=request.email,
            password=request.password,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    db: DatabaseSession,
):
    user = auth_service.authenticate_user(
        db=db,
        email=form_data.username,
        password=form_data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    access_token = (
        auth_service.create_user_token(user)
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def read_current_user(
    current_user: CurrentUser,
):
    return current_user