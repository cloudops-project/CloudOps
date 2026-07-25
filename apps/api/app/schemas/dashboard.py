from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import (
    ComplianceAssessmentStatus,
    FindingSeverity,
    FindingStatus,
    RiskPriority,
)
from app.schemas.common import ApiModel


class DashboardCountItem(ApiModel):
    key: str
    count: int = Field(ge=0)


class DashboardMetadata(ApiModel):
    organization_id: uuid.UUID
    generated_at: datetime
    is_partial: bool
    missing_sections: list[str]


class DashboardAccountPosture(ApiModel):
    total_accounts: int = Field(ge=0)
    connected_accounts: int = Field(ge=0)
    disconnected_accounts: int = Field(ge=0)
    accounts_requiring_attention: int = Field(ge=0)


class DashboardAssetInventory(ApiModel):
    total_assets: int = Field(ge=0)
    active_assets: int = Field(ge=0)
    inactive_assets: int = Field(ge=0)
    counts_by_type: list[DashboardCountItem]
    counts_by_region: list[DashboardCountItem]


class DashboardRecentFinding(ApiModel):
    id: uuid.UUID
    aws_account_id: uuid.UUID
    asset_id: uuid.UUID | None
    rule_key: str
    severity: FindingSeverity
    status: FindingStatus
    service: str
    region: str | None
    last_seen_at: datetime


class DashboardFindingPosture(ApiModel):
    open_total: int = Field(ge=0)
    resolved_total: int = Field(ge=0)
    suppressed_total: int = Field(ge=0)
    open_by_severity: list[DashboardCountItem]
    open_by_service: list[DashboardCountItem]
    open_by_account: list[DashboardCountItem]
    recent_critical_and_high_findings: list[DashboardRecentFinding]


class DashboardCompliancePosture(ApiModel):
    assessment_id: uuid.UUID | None
    framework_key: str | None
    framework_name: str | None
    framework_version: str | None
    assessment_status: ComplianceAssessmentStatus | None
    evaluation_time: datetime | None
    controls_total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    not_assessed: int = Field(ge=0)
    error: int = Field(ge=0)
    pass_percentage: float | None = Field(default=None, ge=0, le=100)


class DashboardRiskTrendPoint(ApiModel):
    assessment_id: uuid.UUID
    evaluation_time: datetime
    aggregate_score: int = Field(ge=0, le=100)
    aggregate_priority: RiskPriority


class DashboardAccountRiskHeatmapItem(ApiModel):
    aws_account_id: uuid.UUID
    account_display_identifier: str
    score: int = Field(ge=0, le=100)
    priority: RiskPriority
    findings_total: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    high_count: int = Field(ge=0)


class DashboardRiskPosture(ApiModel):
    assessment_id: uuid.UUID | None
    evaluation_time: datetime | None
    aggregate_score: int | None = Field(default=None, ge=0, le=100)
    aggregate_priority: RiskPriority | None
    findings_total: int = Field(ge=0)
    severity_counters: list[DashboardCountItem]
    highest_risk_accounts: list[DashboardAccountRiskHeatmapItem]
    trend: list[DashboardRiskTrendPoint]


class DashboardFreshnessItem(ApiModel):
    id: uuid.UUID | None
    status: str | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    evaluation_time: datetime | None = None


class DashboardOperationalFreshness(ApiModel):
    latest_completed_discovery: DashboardFreshnessItem | None
    latest_discovery: DashboardFreshnessItem | None
    latest_completed_evaluation: DashboardFreshnessItem | None
    latest_evaluation: DashboardFreshnessItem | None
    latest_completed_compliance_assessment: DashboardFreshnessItem | None
    latest_compliance_assessment: DashboardFreshnessItem | None
    latest_completed_risk_assessment: DashboardFreshnessItem | None
    latest_risk_assessment: DashboardFreshnessItem | None


class DashboardSummaryResponse(ApiModel):
    metadata: DashboardMetadata
    accounts: DashboardAccountPosture
    assets: DashboardAssetInventory
    findings: DashboardFindingPosture
    compliance: DashboardCompliancePosture
    risk: DashboardRiskPosture
    account_risk_heatmap: list[DashboardAccountRiskHeatmapItem]
    freshness: DashboardOperationalFreshness
