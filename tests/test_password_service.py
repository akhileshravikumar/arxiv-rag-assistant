from app.services.password_service import (
    hash_password,
    verify_password,
)


def test_password_is_hashed():
    plain_password = "StrongPassword123!"

    hashed_password = hash_password(
        plain_password
    )

    assert hashed_password != plain_password
    assert plain_password not in hashed_password


def test_correct_password_is_verified():
    plain_password = "StrongPassword123!"

    hashed_password = hash_password(
        plain_password
    )

    assert verify_password(
        plain_password,
        hashed_password,
    )


def test_wrong_password_is_rejected():
    hashed_password = hash_password(
        "StrongPassword123!"
    )

    assert not verify_password(
        "WrongPassword123!",
        hashed_password,
    )