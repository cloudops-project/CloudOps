from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.models.enums import JiraIntegrationStatus
from app.schemas.common import ApiModel


class JiraIntegrationCreate(ApiModel):
    base_url: str = Field(min_length=8, max_length=500)
    project_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    default_issue_type: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    api_token: str = Field(min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Jira base_url must be an HTTPS URL")
        return value.rstrip("/")


class JiraIntegrationUpdate(ApiModel):
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    project_key: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"
    )
    default_issue_type: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    api_token: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Jira base_url must be an HTTPS URL")
        return value.rstrip("/") if value else value

    @model_validator(mode="after")
    def at_least_one_change(self) -> JiraIntegrationUpdate:
        if all(
            value is None
            for value in (
                self.base_url,
                self.project_key,
                self.default_issue_type,
                self.email,
                self.api_token,
                self.enabled,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self


class JiraIntegrationResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    base_url: str
    project_key: str
    default_issue_type: str
    email: str
    enabled: bool
    status: JiraIntegrationStatus
    last_validated_at: datetime | None
    failure_reason: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class JiraIssueLinkResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    jira_integration_id: uuid.UUID
    finding_id: uuid.UUID | None
    remediation_request_id: uuid.UUID | None
    idempotency_key: str
    issue_key: str
    issue_url: str
    created_by_user_id: uuid.UUID
    created_at: datetime


class JiraIssueCreateRequest(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    remediation_request_id: uuid.UUID | None = None
