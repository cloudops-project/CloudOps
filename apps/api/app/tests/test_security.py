from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.exceptions.errors import AppError, AuthenticationError
from app.models.enums import OrganizationRole
from app.schemas.organization import validate_slug
from app.security.passwords import hash_password, validate_password, verify_password
from app.security.rate_limit import InMemoryRateLimiter
from app.security.rbac import can_assign_role, ensure_actor_can_manage_membership
from app.security.tokens import create_access_token, decode_access_token, hash_opaque_token


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite://",
        "jwt_secret_key": "test-secret-key-that-is-at-least-32-characters",
        "app_env": "testing",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_password_hashing_policy_and_verification() -> None:
    hashed = hash_password("Strong-Password-123!")
    assert hashed != "Strong-Password-123!"
    assert verify_password("Strong-Password-123!", hashed)
    assert not verify_password("wrong", hashed)
    with pytest.raises(AppError):
        validate_password("short")


def test_jwt_creation_expiry_and_invalid_signature() -> None:
    user_id = uuid.uuid4()
    configured = settings()
    token = create_access_token(user_id, configured)
    assert decode_access_token(token, configured).user_id == user_id
    expired = create_access_token(user_id, configured, datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(AuthenticationError):
        decode_access_token(expired, configured)
    with pytest.raises(AuthenticationError):
        decode_access_token(
            token, settings(jwt_secret_key="different-secret-key-that-is-at-least-32")
        )


def test_token_hash_role_policy_and_slug() -> None:
    assert hash_opaque_token("token") == hash_opaque_token("token")
    assert hash_opaque_token("token") != "token"
    assert can_assign_role(OrganizationRole.OWNER, OrganizationRole.OWNER)
    assert can_assign_role(OrganizationRole.ADMIN, OrganizationRole.AUDITOR)
    assert not can_assign_role(OrganizationRole.ADMIN, OrganizationRole.OWNER)
    with pytest.raises(AppError):
        ensure_actor_can_manage_membership(
            actor_role=OrganizationRole.ADMIN,
            target_role=OrganizationRole.OWNER,
        )
    assert validate_slug("example-org") == "example-org"
    with pytest.raises(ValueError):
        validate_slug("Bad Slug")


def test_configuration_security_validation() -> None:
    with pytest.raises((ValidationError, ValueError)):
        settings(app_env="production", cookie_secure=False)
    with pytest.raises((ValidationError, ValueError)):
        settings(jwt_secret_key="short")


def test_authentication_rate_limit_abstraction() -> None:
    limiter = InMemoryRateLimiter(1)
    limiter.check("client:login")
    with pytest.raises(AppError):
        limiter.check("client:login")
