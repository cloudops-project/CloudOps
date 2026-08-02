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

    app_env: Literal["development", "testing", "staging", "production"] = "development"
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
    allow_insecure_staging_transport: bool = False
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"
    auth_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    aws_trusted_principal_arn: str = ""
    aws_trusted_principal_arns: str = ""
    aws_role_session_name: str = "CloudOpsConnectionValidation"
    aws_role_session_duration_seconds: int = Field(default=900, ge=900, le=3600)
    aws_credential_refresh_window_seconds: int = Field(default=60, ge=30, le=600)
    aws_discovery_regions: str = "us-east-1,us-west-2,eu-west-1,ap-south-1"
    aws_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    aws_read_timeout_seconds: int = Field(default=30, ge=1, le=120)
    aws_max_retry_attempts: int = Field(default=3, ge=1, le=10)
    aws_retry_mode: Literal["standard", "adaptive"] = "standard"
    ai_provider: Literal["mock", "bedrock", "external"] = "mock"
    ai_provider_api_key: SecretStr = SecretStr("")
    aws_bedrock_enabled: bool = False
    aws_bedrock_region: str = "us-east-1"
    aws_bedrock_model_id: str = ""
    aws_bedrock_max_tokens: int = Field(default=1200, ge=128, le=4096)
    aws_bedrock_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    aws_bedrock_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    aws_bedrock_read_timeout_seconds: int = Field(default=30, ge=1, le=120)
    aws_bedrock_max_retry_attempts: int = Field(default=2, ge=1, le=5)
    aws_bedrock_max_request_bytes: int = Field(default=65_536, ge=4096, le=262_144)
    aws_bedrock_max_response_bytes: int = Field(default=32_768, ge=4096, le=131_072)
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
    aws_ses_enabled: bool = False
    aws_ses_region: str = "us-east-1"
    aws_ses_from_email: str = ""
    aws_ses_from_name: str = ""
    aws_ses_configuration_set: str = ""
    aws_ses_reply_to: str = ""
    aws_ses_max_recipients: int = Field(default=25, ge=1, le=50)
    aws_ses_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    aws_ses_read_timeout_seconds: int = Field(default=30, ge=1, le=120)
    aws_ses_max_retry_attempts: int = Field(default=3, ge=1, le=5)
    remediation_execution_enabled: bool = False
    remediation_live_aws_enabled: bool = False
    remediation_emergency_stop: bool = True
    # Demo-only escape hatch: replay persisted synthetic inventory instead of
    # assuming a customer role and calling AWS. Refused in production-like
    # environments by model_post_init so it can never silently disable real
    # discovery in a deployed system.
    demo_synthetic_discovery: bool = False
    # Demo-only: accept a genuinely same-origin Origin on the cookie-authenticated
    # POST routes by comparing it to X-Forwarded-Host/-Proto from the reverse
    # proxy. Lets an ephemeral public hostname (Cloudflare Quick Tunnel) work
    # without CORS edits. Refused in production-like environments because
    # X-Forwarded-* is only trustworthy behind a trusted proxy on every path.
    trust_forwarded_host_same_origin: bool = False
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
    # Global kill switch: when false, no organization may configure, read, or use
    # a Jira connection, and no outbound call to Jira Cloud can occur, regardless
    # of what is stored in jira_integrations. Per-organization connection details
    # (base URL, project key, API token) are never global settings; they live in
    # the jira_integrations table. This mirrors AWS_SES_ENABLED/AWS_BEDROCK_ENABLED:
    # an environment-level permission gate in front of tenant-scoped configuration.
    jira_enabled: bool = False
    # Symmetric key (32 raw bytes, base64/url-safe-base64 encoded) used to encrypt
    # per-organization Jira API tokens at rest via app.security.secret_box. This is
    # an application-level stopgap: production deployments must source this from a
    # KMS-backed secret (e.g. AWS Secrets Manager with envelope encryption), not a
    # static environment variable committed anywhere.
    jira_token_encryption_key: SecretStr = SecretStr("")
    jira_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    jira_read_timeout_seconds: int = Field(default=15, ge=1, le=60)
    jira_max_retry_attempts: int = Field(default=3, ge=1, le=5)

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
        production_like = self.app_env in {"staging", "production"}
        if (self.jwt_previous_secret_key is None) != (self.jwt_previous_key_id is None):
            raise ValueError(
                "JWT_PREVIOUS_SECRET_KEY and JWT_PREVIOUS_KEY_ID must be configured together"
            )
        if (
            self.jwt_previous_key_id is not None
            and self.jwt_previous_key_id == self.jwt_active_key_id
        ):
            raise ValueError("JWT key identifiers must be distinct")
        if self.allow_insecure_staging_transport and self.app_env != "staging":
            raise ValueError(
                "ALLOW_INSECURE_STAGING_TRANSPORT is permitted only when APP_ENV=staging"
            )
        if (
            production_like
            and not self.allow_insecure_staging_transport
            and not self.cookie_secure
        ):
            raise ValueError("COOKIE_SECURE must be true in production-like environments")
        if production_like:
            static_variables = (
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
            )
            if any(variable in os.environ for variable in static_variables):
                raise ValueError(
                    "Static AWS credentials are forbidden in production-like environments; "
                    "use the workload credential provider chain"
                )
            if self.ai_provider == "external" and not self.ai_provider_api_key.get_secret_value():
                raise ValueError("AI_PROVIDER_API_KEY is required for the external AI provider")
            if self.ai_provider == "bedrock" and (
                not self.aws_bedrock_enabled or not self.aws_bedrock_model_id.strip()
            ):
                raise ValueError(
                    "AWS_BEDROCK_ENABLED and AWS_BEDROCK_MODEL_ID are required "
                    "for the Bedrock provider"
                )
            if (
                self.notification_provider == "smtp"
                and not self.smtp_password.get_secret_value()
            ):
                raise ValueError("SMTP_PASSWORD is required for the SMTP provider")
            if self.notification_provider == "ses" and (
                not self.aws_ses_enabled or not self.aws_ses_from_email.strip()
            ):
                raise ValueError(
                    "AWS_SES_ENABLED and AWS_SES_FROM_EMAIL are required for the SES provider"
                )
        if production_like and self.demo_synthetic_discovery:
            raise ValueError(
                "DEMO_SYNTHETIC_DISCOVERY is a local demo control and is forbidden in "
                "production-like environments; real discovery must assume the customer role"
            )
        if production_like and self.trust_forwarded_host_same_origin:
            raise ValueError(
                "TRUST_FORWARDED_HOST_SAME_ORIGIN is a local demo control and is forbidden "
                "in production-like environments; configure CORS_ALLOWED_ORIGINS with the "
                "real browser-facing origin instead"
            )
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none")
        if (
            production_like
            and not self.allow_insecure_staging_transport
            and any(
            urlsplit(origin).scheme != "https" for origin in self.allowed_origins
            )
        ):
            raise ValueError("Production-like CORS_ALLOWED_ORIGINS must use HTTPS")
        if self.hsts_enabled and (not production_like or not self.cookie_secure):
            raise ValueError(
                "HSTS_ENABLED requires a production-like APP_ENV and COOKIE_SECURE=true; "
                "enable it only when HTTPS is guaranteed by deployment"
            )
        if production_like and self.notification_provider == "smtp":
            if self.smtp_security == "none" and not self.smtp_use_tls:
                raise ValueError("Production SMTP requires STARTTLS or implicit TLS")
            if self.smtp_username and not self.smtp_password.get_secret_value():
                raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured")
        if (
            production_like
            and self.notification_provider == "slack"
            and not _validate_provider_endpoint(
                self.slack_webhook_url.get_secret_value(), ("hooks.slack.com",)
            )
        ):
            raise ValueError("SLACK_WEBHOOK_URL must be an approved HTTPS endpoint")
        if (
            production_like
            and self.notification_provider == "teams"
            and not _validate_provider_endpoint(
                self.teams_webhook_url.get_secret_value(),
                ("webhook.office.com", "logic.azure.com", "powerautomate.com"),
            )
        ):
            raise ValueError("TEAMS_WEBHOOK_URL must be an approved HTTPS endpoint")
        if self.jira_enabled and not self.jira_token_encryption_key.get_secret_value():
            raise ValueError(
                "JIRA_TOKEN_ENCRYPTION_KEY is required when JIRA_ENABLED is true"
            )

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
    def bedrock_client_config(self) -> Config:
        return Config(
            connect_timeout=self.aws_bedrock_connect_timeout_seconds,
            read_timeout=self.aws_bedrock_read_timeout_seconds,
            retries={
                "total_max_attempts": self.aws_bedrock_max_retry_attempts,
                "mode": "standard",
            },
        )

    @property
    def ses_client_config(self) -> Config:
        return Config(
            connect_timeout=self.aws_ses_connect_timeout_seconds,
            read_timeout=self.aws_ses_read_timeout_seconds,
            retries={
                "total_max_attempts": self.aws_ses_max_retry_attempts,
                "mode": "standard",
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
