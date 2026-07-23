from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingSeverity,
    FindingStatus,
    RiskAssessmentStatus,
    RiskCriticality,
    RiskEnvironment,
    RiskPriority,
)
from app.schemas.common import ApiModel


class RiskAssessmentRequest(ApiModel):
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID | None = None
    evaluation_time: datetime | None = None


class RiskAssessmentResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID | None
    policy_id: uuid.UUID
    evaluation_time: datetime
    source_cutoff_at: datetime
    status: RiskAssessmentStatus
    findings_total: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    informational_count: int
    accounts_scored: int
    aggregate_score: int | None
    aggregate_priority: RiskPriority | None
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class RiskAssessmentListResponse(ApiModel):
    items: list[RiskAssessmentResponse]
    total: int
    page: int
    page_size: int


class RiskPolicyResponse(ApiModel):
    id: uuid.UUID
    key: str
    version: int
    name: str
    description: str
    weights_json: dict[str, Any]
    bands_json: dict[str, Any]
    active: bool
    created_at: datetime


class FindingRiskResponse(ApiModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    finding_id: uuid.UUID
    asset_id: uuid.UUID | None
    source_finding_version: int
    source_finding_status: FindingStatus
    policy_key: str
    policy_version: int
    evaluation_time: datetime
    risk_score: int
    priority: RiskPriority
    severity_points: int
    exposure_points: int
    exploitability_points: int
    privilege_points: int
    asset_criticality_points: int
    environment_points: int
    business_impact_points: int
    data_sensitivity_points: int
    age_points: int
    compensating_adjustment: int
    component_codes_json: dict[str, str]
    unknown_inputs_json: list[str]
    created_at: datetime


class FindingRiskListItem(FindingRiskResponse):
    severity: FindingSeverity
    rule_key: str
    finding_status: FindingStatus
    asset_name: str | None = None
    service: str
    region: str | None = None
    business_impact: BusinessImpact


class FindingRiskListResponse(ApiModel):
    items: list[FindingRiskListItem]
    total: int
    page: int
    page_size: int


class AccountRiskResponse(ApiModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    evaluation_time: datetime
    risk_score: int
    priority: RiskPriority
    highest_finding_score: int
    top_ten_mean: int
    all_findings_mean: int
    findings_total: int
    created_at: datetime


class OrganizationRiskResponse(ApiModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    organization_id: uuid.UUID
    evaluation_time: datetime
    risk_score: int
    priority: RiskPriority
    highest_account_score: int
    mean_account_score: int
    accounts_total: int
    reason_code: str
    created_at: datetime


class RiskSummaryResponse(ApiModel):
    current: OrganizationRiskResponse | None
    assessment: RiskAssessmentResponse | None
    highest_risk_accounts: list[AccountRiskResponse]
    highest_risk_findings: list[FindingRiskListItem]
    highest_risk_assets: list[FindingRiskListItem]
    trend: list[OrganizationRiskResponse]


class RiskContextRequest(ApiModel):
    aws_account_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    criticality: RiskCriticality = RiskCriticality.UNKNOWN
    environment: RiskEnvironment = RiskEnvironment.UNKNOWN
    business_impact: BusinessImpact = BusinessImpact.UNKNOWN
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    expected_version: int | None = Field(default=None, ge=0)


class RiskContextResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    asset_id: uuid.UUID | None
    criticality: RiskCriticality
    environment: RiskEnvironment
    business_impact: BusinessImpact
    data_sensitivity: DataSensitivity
    source: str
    updated_by_user_id: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class CompensatingControlRequest(ApiModel):
    reason: str = Field(min_length=5, max_length=1000)
    score_adjustment: int = Field(ge=-15, le=-1)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def expiry_has_timezone(self) -> CompensatingControlRequest:
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return self


class CompensatingControlResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    finding_id: uuid.UUID
    reason: str
    score_adjustment: int
    created_by_user_id: uuid.UUID
    expires_at: datetime | None
    active: bool
    created_at: datetime
    updated_at: datetime
