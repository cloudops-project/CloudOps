from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.enums import (
    AssetType,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
)
from app.schemas.common import ApiModel


class RuleResponse(ApiModel):
    key: str
    version: int
    name: str
    description: str
    service: str
    asset_type: AssetType | None
    category: str
    severity: FindingSeverity
    remediation: str
    references: list[str]
    enabled_by_default: bool


class EvaluationRequest(ApiModel):
    discovery_job_id: uuid.UUID | None = None


class EvaluationJobResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    discovery_job_id: uuid.UUID | None
    full_evaluation: bool
    sequence: int
    status: EvaluationJobStatus
    started_by_user_id: uuid.UUID
    started_at: datetime | None
    finished_at: datetime | None
    assets_evaluated: int
    rules_evaluated: int
    passed_count: int
    failed_count: int
    error_count: int
    not_applicable_count: int
    findings_created: int
    findings_updated: int
    findings_resolved: int
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


class EvaluationJobListResponse(ApiModel):
    items: list[EvaluationJobResponse]
    total: int
    page: int
    page_size: int


class FindingResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    asset_id: uuid.UUID | None
    rule_key: str
    rule_version: int
    severity: FindingSeverity
    category: str
    status: FindingStatus
    evidence: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    suppressed_at: datetime | None
    suppressed_until: datetime | None
    suppression_reason: str | None
    suppressed_by_user_id: uuid.UUID | None
    last_evaluation_id: uuid.UUID
    lifecycle_version: int
    created_at: datetime
    updated_at: datetime


class FindingListResponse(ApiModel):
    items: list[FindingResponse]
    total: int
    page: int
    page_size: int


class FindingSummaryItem(ApiModel):
    severity: FindingSeverity
    status: FindingStatus
    count: int


class FindingSummaryResponse(ApiModel):
    total: int
    items: list[FindingSummaryItem]


class FindingSuppressRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=1000)
    suppressed_until: datetime | None = None
