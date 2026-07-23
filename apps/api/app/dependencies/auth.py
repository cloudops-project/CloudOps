from __future__ import annotations

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
