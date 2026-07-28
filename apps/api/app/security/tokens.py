from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from app.core.config import Settings
from app.exceptions.errors import AuthenticationError


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    expires_at: datetime
    token_id: uuid.UUID


def create_access_token(user_id: uuid.UUID, settings: Settings, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_active_key_id},
    )


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    keys: list[str] = []
    try:
        key_id = jwt.get_unverified_header(token).get("kid")
        if key_id is None or key_id == settings.jwt_active_key_id:
            keys.append(settings.jwt_secret_key.get_secret_value())
        if settings.jwt_previous_secret_key is not None and (
            key_id is None or key_id == settings.jwt_previous_key_id
        ):
            keys.append(settings.jwt_previous_secret_key.get_secret_value())
        if not keys:
            raise InvalidTokenError("Unknown JWT key identifier")
        payload = None
        for key in keys:
            try:
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=[settings.jwt_algorithm],
                    options={"require": ["sub", "type", "iat", "exp", "jti"]},
                )
                break
            except InvalidTokenError:
                continue
        if payload is None:
            raise InvalidTokenError("JWT signature verification failed")
        if payload["type"] != "access":
            raise AuthenticationError()
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            token_id=uuid.UUID(payload["jti"]),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise AuthenticationError() from None


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
