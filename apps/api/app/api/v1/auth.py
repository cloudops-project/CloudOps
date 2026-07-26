from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.dependencies.auth import AppSettings, CurrentUser, DbSession, UserRateLimiter
from app.exceptions.errors import AuthenticationError
from app.repositories.data import Repository
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    OrganizationAccessResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter()
_password_change_rate_limit = UserRateLimiter("password_change", limit=5, window_seconds=60)


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


def _set_cookie(response: Response, raw: str, settings: AppSettings) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=f"{settings.api_v1_prefix}/auth",
        max_age=settings.refresh_token_expire_days * 86400,
        expires=settings.refresh_token_expire_days * 86400,
    )


def _clear_cookie(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        domain=settings.cookie_domain,
        path=f"{settings.api_v1_prefix}/auth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _token_response(token: str, settings: AppSettings) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=token, expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession, settings: AppSettings) -> UserResponse:
    user = AuthService(db, settings).register(
        str(payload.email), payload.password, payload.full_name, payload.organization_name
    )
    return UserResponse.model_validate(user)


@router.post("/login", response_model=AccessTokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> AccessTokenResponse:
    user_agent, ip = _client(request)
    tokens = AuthService(db, settings).login(str(payload.email), payload.password, user_agent, ip)
    _set_cookie(response, tokens.refresh_token, settings)
    return _token_response(tokens.access_token, settings)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    request: Request, response: Response, db: DbSession, settings: AppSettings
) -> AccessTokenResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise AuthenticationError("missing_refresh_token", "Refresh token is required.")
    user_agent, ip = _client(request)
    tokens = AuthService(db, settings).refresh(raw, user_agent, ip)
    _set_cookie(response, tokens.refresh_token, settings)
    return _token_response(tokens.access_token, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession, settings: AppSettings) -> None:
    user_agent, ip = _client(request)
    AuthService(db, settings).logout(
        request.cookies.get(settings.refresh_cookie_name), None, user_agent, ip
    )
    _clear_cookie(response, settings)


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser, db: DbSession) -> MeResponse:
    organizations = [
        OrganizationAccessResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role=member.role,
            membership_status=member.status,
        )
        for org, member in Repository(db).user_organizations(user.id)
    ]
    return MeResponse(user=UserResponse.model_validate(user), organizations=organizations)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_password_change_rate_limit)],
)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> None:
    AuthService(db, settings).change_password(user, payload.current_password, payload.new_password)
    _clear_cookie(response, settings)
