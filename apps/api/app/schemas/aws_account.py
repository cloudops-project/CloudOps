from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.models.enums import AWSAccountStatus
from app.schemas.common import ApiModel

REMEDIATION_ROLE_ARN_PATTERN = re.compile(
    r"^arn:(aws|aws-us-gov|aws-cn):iam::(?P<account_id>[0-9]{12}):"
    r"role/(?P<role>[A-Za-z0-9+=,.@_/-]{1,512})$"
)


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


class AWSRemediationRoleConfiguration(ApiModel):
    """Account-aware remediation role validation shared by the admin service."""

    account_id: str = Field(pattern=r"^[0-9]{12}$")
    remediation_role_arn: str = Field(min_length=20, max_length=2048)

    @model_validator(mode="after")
    def role_belongs_to_account(self) -> AWSRemediationRoleConfiguration:
        match = REMEDIATION_ROLE_ARN_PATTERN.fullmatch(self.remediation_role_arn.strip())
        if match is None:
            raise ValueError("AWS remediation role ARN must be an IAM role ARN")
        if match.group("account_id") != self.account_id:
            raise ValueError("AWS remediation role ARN must belong to the configured account")
        self.remediation_role_arn = self.remediation_role_arn.strip()
        return self


class RemediationTrustConfigureRequest(ApiModel):
    remediation_role_arn: str = Field(min_length=20, max_length=2048)


class RemediationAdministrationReason(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class RemediationAdministrationStatus(ApiModel):
    account_id: uuid.UUID
    remediation_trust_configured: bool
    remediation_role_arn_masked: str | None
    sandbox_approved: bool
    sandbox_approved_at: datetime | None
    sandbox_approved_by_user_id: uuid.UUID | None


class RemediationTrustOneTimeResponse(RemediationAdministrationStatus):
    remediation_external_id: str | None = Field(default=None, min_length=32, max_length=128)


class AWSAccountResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    account_id: str
    role_arn: str | None
    status: AWSAccountStatus
    connection_status: AWSAccountStatus
    failure_reason: str | None
    last_validated_at: datetime | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AWSAccountDetailResponse(ApiModel):
    account: AWSAccountResponse


class AWSAccountOnboardingResponse(ApiModel):
    account: AWSAccountResponse
    external_id: str
    trust_policy: dict[str, Any]
    permission_policy: dict[str, str]
    onboarding_instructions: list[str]
