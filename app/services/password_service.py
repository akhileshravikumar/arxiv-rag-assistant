from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Convert a plain-text password into a secure hash.
    """
    if not password:
        raise ValueError("Password cannot be empty.")

    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Check whether a password matches a stored hash.
    """
    if not plain_password or not hashed_password:
        return False

    return password_hash.verify(
        plain_password,
        hashed_password,
    )