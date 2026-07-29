from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.dependencies.auth import UserRateLimiter
from app.exceptions.errors import AppError, AuthenticationError, RateLimitError
from app.models import AuditEvent, User
from app.models.enums import AISourceType, AITaskType, OrganizationRole
from app.schemas.ai import AIGenerateRequest, AISourceInput
from app.schemas.organization import validate_slug
from app.security.passwords import hash_password, validate_password, verify_password
from app.security.rate_limit import InMemoryRateLimiter
from app.security.rbac import can_assign_role, ensure_actor_can_manage_membership
from app.security.tokens import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_opaque_token,
)
from app.services.common import record_audit


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
    independently_salted = hash_password("Strong-Password-123!")
    assert hashed != "Strong-Password-123!"
    assert independently_salted != hashed
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


@pytest.mark.parametrize(
    ("algorithm", "overrides"),
    [
        ("HS512", {}),
        ("HS256", {"type": "refresh"}),
        ("HS256", {"sub": "not-a-uuid"}),
        ("HS256", {"jti": "not-a-uuid"}),
        ("HS256", {"exp": None}),
    ],
)
def test_jwt_rejects_algorithm_confusion_and_invalid_claims(
    algorithm: str, overrides: dict[str, object]
) -> None:
    configured = settings(jwt_secret_key="x" * 64)
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    payload.update(overrides)
    if overrides.get("exp", object()) is None:
        payload.pop("exp")
    token = jwt.encode(
        payload,
        configured.jwt_secret_key.get_secret_value(),
        algorithm=algorithm,
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token, configured)


def test_token_hash_role_policy_and_slug() -> None:
    first = generate_opaque_token()
    second = generate_opaque_token()
    assert first != second
    assert len(first) >= 64
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


def test_insecure_transport_is_explicitly_staging_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises((ValidationError, ValueError), match="APP_ENV=staging"):
        settings(
            app_env="production",
            allow_insecure_staging_transport=True,
            cookie_secure=False,
            cors_allowed_origins="http://temporary.example.invalid",
        )
    with pytest.raises((ValidationError, ValueError), match="COOKIE_SECURE"):
        settings(app_env="staging", cookie_secure=False)

    temporary = settings(
        app_env="staging",
        allow_insecure_staging_transport=True,
        cookie_secure=False,
        hsts_enabled=False,
        cors_allowed_origins="http://temporary.example.invalid",
        frontend_url="http://temporary.example.invalid",
    )
    assert temporary.app_env == "staging"
    assert temporary.cookie_secure is False
    assert temporary.hsts_enabled is False

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-workload-chain-regression")
    with pytest.raises((ValidationError, ValueError), match="Static AWS credentials"):
        settings(
            app_env="staging",
            allow_insecure_staging_transport=True,
            cookie_secure=False,
            cors_allowed_origins="http://temporary.example.invalid",
        )


def test_cors_allowed_origins_rejects_wildcard_and_malformed_values() -> None:
    invalid_origins = (
        "*",
        "http://localhost:5173,*",
        "not-a-valid-origin",
        "http://localhost:5173/some/path",
        "http://localhost:5173?query=value",
        "http://localhost:5173#fragment",
        "http://user@localhost:5173",
        "http://localhost:99999",
        "https://*.example.com",
    )
    for origin in invalid_origins:
        with pytest.raises((ValidationError, ValueError)):
            settings(cors_allowed_origins=origin)
    valid = settings(cors_allowed_origins="http://localhost:5173,https://app.example.com")
    assert valid.allowed_origins == ["http://localhost:5173", "https://app.example.com"]
    with pytest.raises((ValidationError, ValueError)):
        settings(
            app_env="production",
            cookie_secure=True,
            cors_allowed_origins="http://app.example.com",
        )
    production = settings(
        app_env="production",
        cookie_secure=True,
        cors_allowed_origins="https://app.example.com",
    )
    assert production.allowed_origins == ["https://app.example.com"]


def test_authentication_rate_limit_abstraction() -> None:
    limiter = InMemoryRateLimiter(1)
    limiter.check("client:login")
    with pytest.raises(AppError) as caught:
        limiter.check("client:login")
    assert caught.value.status_code == 429
    assert isinstance(caught.value, RateLimitError)
    assert caught.value.retry_after_seconds in range(1, 61)


def test_authentication_rate_limit_http_response_has_retry_after() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.exceptions.handlers import register_exception_handlers
    from app.logging.middleware import (
        AuthenticationRateLimitMiddleware,
        RequestContextMiddleware,
    )

    app = FastAPI()
    app.add_middleware(AuthenticationRateLimitMiddleware, limit=1)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.post("/api/v1/auth/login")
    def login_probe() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    assert client.post("/api/v1/auth/login").status_code == 200
    response = client.post("/api/v1/auth/login")
    assert response.status_code == 429
    assert response.headers["retry-after"] in {str(value) for value in range(1, 61)}
    assert response.json()["error"]["code"] == "rate_limited"


def test_user_rate_limiter_blocks_after_limit_and_is_scoped_per_user() -> None:
    limiter = UserRateLimiter("test_action", limit=2, window_seconds=60)
    prod_settings = settings(
        app_env="production",
        cookie_secure=True,
        cors_allowed_origins="https://app.example.com",
    )
    user_a = cast(User, SimpleNamespace(id=uuid.uuid4()))
    user_b = cast(User, SimpleNamespace(id=uuid.uuid4()))

    limiter(user_a, prod_settings)
    limiter(user_a, prod_settings)
    with pytest.raises(AppError):
        limiter(user_a, prod_settings)

    # A different user has an independent budget.
    limiter(user_b, prod_settings)


def test_user_rate_limiter_is_relaxed_in_testing_env() -> None:
    limiter = UserRateLimiter("test_action_relaxed", limit=1, window_seconds=60)
    user = cast(User, SimpleNamespace(id=uuid.uuid4()))
    for _ in range(5):
        limiter(user, settings())
    prod_settings = settings(
        app_env="production",
        cookie_secure=True,
        cors_allowed_origins="https://app.example.com",
    )
    limiter(user, prod_settings)
    with pytest.raises(AppError):
        limiter(user, prod_settings)


def test_security_headers_middleware_requires_explicit_hsts_guarantee() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.logging.middleware import SecurityHeadersMiddleware

    def build(*, hsts_enabled: bool) -> TestClient:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=hsts_enabled)

        @app.get("/probe")
        def probe() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    prod_response = build(hsts_enabled=True).get("/probe")
    assert (
        prod_response.headers["strict-transport-security"]
        == "max-age=63072000; includeSubDomains"
    )

    dev_response = build(hsts_enabled=False).get("/probe")
    assert "strict-transport-security" not in dev_response.headers


def test_hsts_setting_requires_production_secure_cookie() -> None:
    with pytest.raises((ValidationError, ValueError)):
        settings(hsts_enabled=True)
    with pytest.raises((ValidationError, ValueError)):
        settings(
            app_env="production",
            cookie_secure=False,
            hsts_enabled=True,
            cors_allowed_origins="https://app.example.com",
        )
    configured = settings(
        app_env="production",
        cookie_secure=True,
        hsts_enabled=True,
        cors_allowed_origins="https://app.example.com",
    )
    assert configured.hsts_enabled is True


def test_audit_writer_redacts_sentinel_secrets(db: Session) -> None:
    sentinels = (
        "password=phase1-sentinel-password",
        "api_key=phase1-sentinel-api-key",  # gitleaks:allow
        "Bearer phase1-sentinel-jwt",
        "postgresql://user:phase1-sentinel-db-password@example.invalid/cloudops",
    )
    record_audit(
        db,
        "security.sentinel",
        "test",
        metadata={
            "values": list(sentinels),
            "secret_access_key": "phase1-sentinel-aws-secret",  # gitleaks:allow
        },
        user_agent=" ".join(sentinels),
    )
    db.commit()
    event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "security.sentinel"))
    assert event is not None
    persisted = f"{event.metadata_json} {event.user_agent}"
    for sentinel in sentinels:
        assert sentinel not in persisted
    assert "phase1-sentinel-aws-secret" not in persisted


@pytest.mark.parametrize(
    "options",
    [
        {"x" * 65: "value"},
        {"tone": "x" * 501},
        {"count": 1_000_001},
    ],
)
def test_ai_options_are_bounded(options: dict[str, str | int]) -> None:
    with pytest.raises(ValidationError):
        AIGenerateRequest(
            organization_id=uuid.uuid4(),
            task_type=AITaskType.EXPLAIN_FINDING,
            sources=[
                AISourceInput(source_type=AISourceType.FINDING, source_id=uuid.uuid4())
            ],
            idempotency_key="phase1-options",
            options=options,
        )
