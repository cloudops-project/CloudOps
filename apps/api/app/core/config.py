from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from botocore.config import Config  # type: ignore[import-untyped]
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_origin(origin: str) -> None:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"CORS_ALLOWED_ORIGINS contains a malformed origin: {origin!r}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"CORS_ALLOWED_ORIGINS contains a malformed origin: {origin!r}")
    host = parsed.hostname
    if "*" in host or len(host) > 253:
        raise ValueError(f"CORS_ALLOWED_ORIGINS contains a malformed origin: {origin!r}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if any(
            not label
            or len(label) > 63
            or label[0] == "-"
            or label[-1] == "-"
            or not all(character.isalnum() or character == "-" for character in label)
            for label in labels
        ):
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS contains a malformed origin: {origin!r}"
            ) from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"CORS_ALLOWED_ORIGINS contains an invalid port: {origin!r}")


def _validate_provider_endpoint(value: str, allowed_hosts: tuple[str, ...]) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    return bool(
        parsed.scheme == "https"
        and host
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_hosts)
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "testing", "production"] = "development"
    app_name: str = "CloudOps API"
    api_v1_prefix: str = "/api/v1"
    database_url: SecretStr
    migration_database_url: SecretStr | None = None
    jwt_secret_key: SecretStr
    jwt_active_key_id: str = Field(default="primary", min_length=1, max_length=64)
    jwt_previous_secret_key: SecretStr | None = None
    jwt_previous_key_id: str | None = Field(default=None, min_length=1, max_length=64)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    invitation_token_expire_hours: int = Field(default=72, ge=1, le=168)
    cors_allowed_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    hsts_enabled: bool = False
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"
    auth_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    aws_trusted_principal_arn: str = ""
    aws_role_session_name: str = "CloudOpsConnectionValidation"
    aws_role_session_duration_seconds: int = Field(default=900, ge=900, le=3600)
    aws_credential_refresh_window_seconds: int = Field(default=60, ge=30, le=600)
    aws_discovery_regions: str = "us-east-1,us-west-2,eu-west-1,ap-south-1"
    aws_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    aws_read_timeout_seconds: int = Field(default=30, ge=1, le=120)
    aws_max_retry_attempts: int = Field(default=3, ge=1, le=10)
    aws_retry_mode: Literal["standard", "adaptive"] = "standard"
    ai_provider: Literal["mock", "external"] = "mock"
    ai_provider_api_key: SecretStr = SecretStr("")
    notification_provider: Literal["mock", "smtp", "ses", "slack", "teams"] = "mock"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = "cloudops-demo@example.local"
    smtp_from_name: str = "CloudOps Demo"
    smtp_use_tls: bool = False
    smtp_security: Literal["none", "starttls", "implicit"] = "none"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    notification_max_message_bytes: int = Field(
        default=262_144, ge=1024, le=1_048_576
    )
    slack_webhook_url: SecretStr = SecretStr("")
    teams_webhook_url: SecretStr = SecretStr("")
    webhook_timeout_seconds: int = Field(default=10, ge=1, le=60)
    scheduler_batch_size: int = Field(default=100, ge=1, le=1000)
    scheduler_poll_interval_seconds: float = Field(default=15.0, ge=1, le=300)
    job_lease_seconds: int = Field(default=120, ge=15, le=3600)
    job_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    job_shutdown_grace_seconds: int = Field(default=30, ge=1, le=300)
    notification_provider_api_key: SecretStr = SecretStr("")

    @field_validator("jwt_secret_key", "jwt_previous_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT signing keys must contain at least 32 characters")
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/' and omit a trailing slash")
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must not contain a wildcard; "
                    "the API sends allow_credentials=True, and a wildcard origin "
                    "combined with credentials is a cross-origin misconfiguration"
                )
            _validate_origin(origin)
        return value

    def model_post_init(self, __context: object) -> None:
        if (self.jwt_previous_secret_key is None) != (self.jwt_previous_key_id is None):
            raise ValueError(
                "JWT_PREVIOUS_SECRET_KEY and JWT_PREVIOUS_KEY_ID must be configured together"
            )
        if (
            self.jwt_previous_key_id is not None
            and self.jwt_previous_key_id == self.jwt_active_key_id
        ):
            raise ValueError("JWT key identifiers must be distinct")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.app_env == "production":
            static_variables = (
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
            )
            if any(variable in os.environ for variable in static_variables):
                raise ValueError(
                    "Static AWS credentials are forbidden in production; "
                    "use the workload credential provider chain"
                )
            if self.ai_provider == "external" and not self.ai_provider_api_key.get_secret_value():
                raise ValueError("AI_PROVIDER_API_KEY is required for the external AI provider")
            if (
                self.notification_provider == "smtp"
                and not self.smtp_password.get_secret_value()
            ):
                raise ValueError("SMTP_PASSWORD is required for the SMTP provider")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none")
        if self.app_env == "production" and any(
            urlsplit(origin).scheme != "https" for origin in self.allowed_origins
        ):
            raise ValueError("Production CORS_ALLOWED_ORIGINS must use HTTPS")
        if self.hsts_enabled and (self.app_env != "production" or not self.cookie_secure):
            raise ValueError(
                "HSTS_ENABLED requires APP_ENV=production and COOKIE_SECURE=true; "
                "enable it only when HTTPS is guaranteed by deployment"
            )
        if self.app_env == "production" and self.notification_provider == "smtp":
            if self.smtp_security == "none" and not self.smtp_use_tls:
                raise ValueError("Production SMTP requires STARTTLS or implicit TLS")
            if self.smtp_username and not self.smtp_password.get_secret_value():
                raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured")
        if (
            self.app_env == "production"
            and self.notification_provider == "slack"
            and not _validate_provider_endpoint(
                self.slack_webhook_url.get_secret_value(), ("hooks.slack.com",)
            )
        ):
            raise ValueError("SLACK_WEBHOOK_URL must be an approved HTTPS endpoint")
        if (
            self.app_env == "production"
            and self.notification_provider == "teams"
            and not _validate_provider_endpoint(
                self.teams_webhook_url.get_secret_value(),
                ("webhook.office.com", "logic.azure.com", "powerautomate.com"),
            )
        ):
            raise ValueError("TEAMS_WEBHOOK_URL must be an approved HTTPS endpoint")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def refresh_cookie_name(self) -> str:
        return "cloudops_refresh_token"

    @property
    def discovery_regions(self) -> list[str]:
        return [
            region.strip() for region in self.aws_discovery_regions.split(",") if region.strip()
        ]

    @property
    def aws_client_config(self) -> Config:
        return Config(
            connect_timeout=self.aws_connect_timeout_seconds,
            read_timeout=self.aws_read_timeout_seconds,
            retries={
                "total_max_attempts": self.aws_max_retry_attempts,
                "mode": self.aws_retry_mode,
            },
        )

    @property
    def database_dsn(self) -> str:
        """Reveal the database DSN only at the SQLAlchemy integration boundary."""
        return self.database_url.get_secret_value()

    @property
    def migration_database_dsn(self) -> str:
        """Use a separately injected migration credential when configured."""
        value = self.migration_database_url or self.database_url
        return value.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
