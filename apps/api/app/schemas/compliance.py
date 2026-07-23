from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import ComplianceAssessmentStatus, ComplianceControlStatus
from app.schemas.common import ApiModel


class FrameworkResponse(ApiModel):
    id: uuid.UUID
    key: str
    name: str
    version: str
    description: str
    official_reference: str
    enabled: bool


class ControlResponse(ApiModel):
    id: uuid.UUID
    framework_id: uuid.UUID
    control_key: str
    title: str
    description: str
    section: str | None


class RuleControlMappingResponse(ApiModel):
    id: uuid.UUID
    rule_key: str
    minimum_rule_version: int
    maximum_rule_version: int | None
    framework_id: uuid.UUID
    control_id: uuid.UUID
    mapping_type: str
    rationale: str


class AssessmentRequest(ApiModel):
    framework_key: str = Field(min_length=2, max_length=64)
    framework_version: str | None = Field(default=None, max_length=64)
    evaluation_job_id: uuid.UUID | None = None


class AssessmentResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID | None
    framework_id: uuid.UUID
    status: ComplianceAssessmentStatus
    controls_total: int
    controls_passed: int
    controls_failed: int
    controls_not_assessed: int
    controls_error: int
    findings_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str | None


class AssessmentListResponse(ApiModel):
    items: list[AssessmentResponse]
    total: int
    page: int
    page_size: int


class AssessmentControlResponse(ApiModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    control_id: uuid.UUID
    framework_id: uuid.UUID
    status: ComplianceControlStatus
    findings_count: int
    assessed_at: datetime


class AssessmentDetailResponse(AssessmentResponse):
    controls: list[AssessmentControlResponse]


class ControlFindingResponse(ApiModel):
    control: ControlResponse
    status: ComplianceControlStatus | None = None
    finding_ids: list[uuid.UUID]
    total: int
    page: int
    page_size: int


class ComplianceSummaryResponse(ApiModel):
    assessments_total: int
    controls_passed: int
    controls_failed: int
    controls_not_assessed: int
    controls_error: int
