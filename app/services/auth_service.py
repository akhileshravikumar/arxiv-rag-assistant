from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.password_service import (
    hash_password,
    verify_password,
)
from app.services.token_service import TokenService


class AuthService:
    def __init__(
        self,
        token_service: TokenService,
    ) -> None:
        self.token_service = token_service

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def register_user(
        self,
        db: Session,
        email: str,
        password: str,
    ) -> User:
        normalized_email = self.normalize_email(
            email
        )

        existing_user = db.scalar(
            select(User).where(
                User.email == normalized_email
            )
        )

        if existing_user is not None:
            raise ValueError(
                "An account with this email already exists."
            )

        user = User(
            email=normalized_email,
            hashed_password=hash_password(
                password
            ),
            role="user",
            is_active=True,
        )

        db.add(user)

        try:
            db.commit()
            db.refresh(user)

        except Exception:
            db.rollback()
            raise

        return user

    def authenticate_user(
        self,
        db: Session,
        email: str,
        password: str,
    ) -> User | None:
        normalized_email = self.normalize_email(
            email
        )

        user = db.scalar(
            select(User).where(
                User.email == normalized_email
            )
        )

        if user is None:
            return None

        if not verify_password(
            password,
            user.hashed_password,
        ):
            return None

        if not user.is_active:
            return None

        return user

    def create_user_token(
        self,
        user: User,
    ) -> str:
        return self.token_service.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
        )