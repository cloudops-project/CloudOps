from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.enums import RemediationExecutionMode, RemediationStatus
from app.schemas.common import ApiModel


class RemediationRequestResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    finding_id: uuid.UUID
    rule_key: str
    rule_version: int
    action_key: str
    action_version: int
    idempotency_key: str
    requested_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    rejected_by_user_id: uuid.UUID | None
    status: RemediationStatus
    execution_mode: RemediationExecutionMode
    automation_eligible: bool
    title: str
    summary: str
    remediation_steps_json: list[str]
    verification_steps_json: list[str]
    rollback_steps_json: list[str]
    preview_json: dict[str, Any]
    request_snapshot_hash: str
    approved_snapshot_hash: str | None
    dry_run: bool
    before_state_json: dict[str, Any] | None
    after_state_json: dict[str, Any] | None
    execution_result_json: dict[str, Any] | None
    attempt_count: int
    rejection_reason: str | None
    failure_reason: str | None
    requested_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    executed_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RemediationRequestListResponse(ApiModel):
    items: list[RemediationRequestResponse]
    total: int
    page: int
    page_size: int


class RemediationRejectRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=1000)


class PrepareLiveRemediationRequest(ApiModel):
    """An intentionally empty body; every execution field is server-owned."""
