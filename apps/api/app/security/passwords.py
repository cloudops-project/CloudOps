from __future__ import annotations

import os
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.exceptions.errors import AppError

_testing = os.getenv("APP_ENV", "development").casefold() == "testing"
_hasher = PasswordHasher(
    time_cost=1 if _testing else 3,
    memory_cost=8192 if _testing else 65536,
    parallelism=1 if _testing else 4,
    hash_len=32,
    salt_len=16,
)
_special = re.compile(r"[^\w\s]", re.UNICODE)


def validate_password(password: str, email: str | None = None) -> None:
    failures: list[str] = []
    if len(password) < 12:
        failures.append("at least 12 characters")
    if len(password) > 128:
        failures.append("at most 128 characters")
    if not any(char.isupper() for char in password):
        failures.append("an uppercase character")
    if not any(char.islower() for char in password):
        failures.append("a lowercase character")
    if not any(char.isdigit() for char in password):
        failures.append("a number")
    if not _special.search(password):
        failures.append("a symbol")
    if email and email.split("@", 1)[0].casefold() in password.casefold():
        failures.append("no email-name inclusion")
    if failures:
        raise AppError(
            "weak_password",
            "Password must include " + ", ".join(failures) + ".",
            422,
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


DUMMY_PASSWORD_HASH = hash_password("CloudOps-Dummy-Password-123!")
