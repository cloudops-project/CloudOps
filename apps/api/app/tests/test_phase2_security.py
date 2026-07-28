from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.exceptions.errors import AuthenticationError
from app.security.tokens import create_access_token, decode_access_token


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "testing",
        "database_url": "sqlite://",
        "jwt_secret_key": "phase2-active-key-with-at-least-32-characters",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "database_url": "postgresql://cloudops:synthetic@example.invalid/cloudops",
        "jwt_secret_key": "phase2-production-key-with-at-least-32-characters",
        "cookie_secure": True,
        "cors_allowed_origins": "https://cloudops.example.invalid",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "variable",
    ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"),
)
def test_production_rejects_static_aws_credential_environment(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "synthetic-value-never-used")
    with pytest.raises((ValidationError, ValueError), match="Static AWS credentials"):
        production_settings()


def test_secret_settings_are_redacted() -> None:
    configured = settings(
        database_url="postgresql://cloudops:phase2-db-sentinel@example.invalid/cloudops",
        smtp_password="phase2-smtp-sentinel",
        ai_provider_api_key="phase2-ai-sentinel",
        notification_provider_api_key="phase2-notification-sentinel",  # gitleaks:allow
    )
    rendered = repr(configured)
    for sentinel in (
        "phase2-db-sentinel",
        "phase2-smtp-sentinel",
        "phase2-ai-sentinel",
        "phase2-notification-sentinel",
        "phase2-active-key",
    ):
        assert sentinel not in rendered


def test_provider_secrets_are_required_only_when_provider_is_enabled() -> None:
    with pytest.raises((ValidationError, ValueError), match="AI_PROVIDER_API_KEY"):
        production_settings(ai_provider="external")
    with pytest.raises((ValidationError, ValueError), match="SMTP_PASSWORD"):
        production_settings(notification_provider="smtp", smtp_username="mailer")


def test_jwt_key_rotation_overlap_and_retirement() -> None:
    user_id = uuid.uuid4()
    old = settings(
        jwt_secret_key="phase2-previous-key-with-at-least-32-characters",  # gitleaks:allow
        jwt_active_key_id="previous",
    )
    old_token = create_access_token(user_id, old)

    overlap = settings(
        jwt_secret_key="phase2-current-key-with-at-least-32-characters",
        jwt_active_key_id="current",
        jwt_previous_secret_key="phase2-previous-key-with-at-least-32-characters",  # gitleaks:allow
        jwt_previous_key_id="previous",
    )
    new_token = create_access_token(user_id, overlap)
    assert jwt.get_unverified_header(new_token)["kid"] == "current"
    assert decode_access_token(old_token, overlap).user_id == user_id
    assert decode_access_token(new_token, overlap).user_id == user_id

    retired = settings(
        jwt_secret_key="phase2-current-key-with-at-least-32-characters",
        jwt_active_key_id="current",
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(old_token, retired)


def test_legacy_jwt_without_kid_is_accepted_during_overlap() -> None:
    configured = settings(
        jwt_secret_key="phase2-current-key-with-at-least-32-characters",
        jwt_active_key_id="current",
        jwt_previous_secret_key="phase2-previous-key-with-at-least-32-characters",  # gitleaks:allow
        jwt_previous_key_id="previous",
    )
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    assert configured.jwt_previous_secret_key is not None
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": str(uuid.uuid4()),
        },
        configured.jwt_previous_secret_key.get_secret_value(),
        algorithm=configured.jwt_algorithm,
    )
    assert decode_access_token(token, configured).user_id == user_id
