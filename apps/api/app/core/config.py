from __future__ import annotations

from functools import lru_cache
from typing import Literal

from botocore.config import Config  # type: ignore[import-untyped]
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    invitation_token_expire_hours: int = Field(default=72, ge=1, le=168)
    cors_allowed_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"
    auth_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    aws_trusted_principal_arn: str = ""
    aws_role_session_name: str = "CloudOpsConnectionValidation"
    aws_discovery_regions: str = "us-east-1,us-west-2,eu-west-1,ap-south-1"
    aws_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    aws_read_timeout_seconds: int = Field(default=30, ge=1, le=120)
    aws_max_retry_attempts: int = Field(default=3, ge=1, le=10)
    aws_retry_mode: Literal["standard", "adaptive"] = "standard"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/' and omit a trailing slash")
        return value

    def model_post_init(self, __context: object) -> None:
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
