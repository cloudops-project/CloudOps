from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.models.enums import AWSAccountStatus
from app.schemas.common import ApiModel


class AWSAccountCreate(ApiModel):
    organization_id: uuid.UUID
    name: str = Field(min_length=2, max_length=160)
    account_id: str = Field(min_length=12, max_length=12)


class AWSAccountUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    role_arn: str | None = Field(default=None, min_length=20, max_length=2048)

    @model_validator(mode="after")
    def at_least_one_change(self) -> AWSAccountUpdate:
        if self.name is None and self.role_arn is None:
            raise ValueError("At least one account field must be provided")
        return self


class AWSAccountResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    account_id: str
    role_arn: str | None
    external_id: str
    status: AWSAccountStatus
    connection_status: AWSAccountStatus
    failure_reason: str | None
    last_validated_at: datetime | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AWSAccountDetailResponse(ApiModel):
    account: AWSAccountResponse
    trust_policy: dict[str, Any]
    permission_policy: dict[str, str]
    onboarding_instructions: list[str]
