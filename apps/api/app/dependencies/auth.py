from __future__ import annotations

import threading
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.exceptions.errors import AuthenticationError
from app.models import User
from app.models.enums import UserStatus
from app.repositories.data import Repository
from app.security.rate_limit import InMemoryRateLimiter
from app.security.tokens import decode_access_token

bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def require_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: DbSession,
    settings: AppSettings,
) -> User:
    if not credentials or credentials.scheme.casefold() != "bearer":
        raise AuthenticationError()
    claims = decode_access_token(credentials.credentials, settings)
    user = Repository(db).user(claims.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthenticationError()
    return user


CurrentUser = Annotated[User, Depends(require_authenticated_user)]


def require_platform_admin(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        from app.exceptions.errors import ForbiddenError

        raise ForbiddenError()
    return user


class UserRateLimiter:
    """Per-user, in-memory, single-process rate limit for authenticated
    routes that are individually expensive or cost-bearing (e.g. calls out
    to a third-party AWS account, or a bounded CSV export) rather than
    brute-force targets. This is a Stage 1 safeguard, not a distributed
    limiter — see AuthenticationRateLimitMiddleware for the equivalent
    caveat on the unauthenticated auth routes. A shared backend (e.g.
    Redis) is required before this is relied upon across multiple API
    instances in production."""

    def __init__(self, name: str, limit: int, window_seconds: int = 60) -> None:
        self._name = name
        self._limit = limit
        self._window_seconds = window_seconds
        self._limiters: dict[int, InMemoryRateLimiter] = {}
        self._lock = threading.Lock()

    def __call__(self, user: CurrentUser, settings: AppSettings) -> None:
        limit = 10000 if settings.app_env == "testing" else self._limit
        with self._lock:
            limiter = self._limiters.get(limit)
            if limiter is None:
                limiter = self._limiters[limit] = InMemoryRateLimiter(
                    limit, self._window_seconds
                )
        limiter.check(
            f"{self._name}:{user.id}",
            message=f"Too many {self._name.replace('_', ' ')} requests. Try again later.",
        )
