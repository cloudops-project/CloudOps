from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountRiskSnapshot,
    Asset,
    AWSAccount,
    ComplianceAssessment,
    ComplianceFramework,
    DiscoveryJob,
    EvaluationJob,
    Finding,
    OrganizationRiskSnapshot,
    RiskAssessment,
)
from app.models.enums import (
    AWSAccountStatus,
    ComplianceAssessmentStatus,
    DiscoveryJobStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    RiskAssessmentStatus,
)
from app.schemas.dashboard import (
    DashboardAccountPosture,
    DashboardAccountRiskHeatmapItem,
    DashboardAssetInventory,
    DashboardCompliancePosture,
    DashboardCountItem,
    DashboardFindingPosture,
    DashboardFreshnessItem,
    DashboardMetadata,
    DashboardOperationalFreshness,
    DashboardRecentFinding,
    DashboardRiskPosture,
    DashboardRiskTrendPoint,
    DashboardSummaryResponse,
)

DISTRIBUTION_LIMIT = 10
RECENT_FINDINGS_LIMIT = 10
ACCOUNT_RISK_LIMIT = 20
RISK_TREND_LIMIT = 12

_SEVERITY_RANK = case(
    {
        FindingSeverity.CRITICAL: 5,
        FindingSeverity.HIGH: 4,
        FindingSeverity.MEDIUM: 3,
        FindingSeverity.LOW: 2,
        FindingSeverity.INFORMATIONAL: 1,
    },
    value=Finding.severity,
    else_=0,
)


class DashboardService:
    """Read-only Stage 8A dashboard aggregation over authoritative Stage 2-7 rows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, organization_id: uuid.UUID) -> DashboardSummaryResponse:
        accounts = self._accounts(organization_id)
        assets = self._assets(organization_id)
        findings = self._findings(organization_id)
        compliance = self._compliance(organization_id)
        risk = self._risk(organization_id)
        heatmap = risk.highest_risk_accounts
        freshness = self._freshness(organization_id)
        missing_sections = self._missing_sections(
            accounts, assets, findings, compliance, risk, freshness
        )
        return DashboardSummaryResponse(
            metadata=DashboardMetadata(
                organization_id=organization_id,
                generated_at=datetime.now(UTC),
                is_partial=bool(missing_sections),
                missing_sections=missing_sections,
            ),
            accounts=accounts,
            assets=assets,
            findings=findings,
            compliance=compliance,
            risk=risk,
            account_risk_heatmap=heatmap,
            freshness=freshness,
        )

    def _accounts(self, organization_id: uuid.UUID) -> DashboardAccountPosture:
        rows = self.db.execute(
            select(AWSAccount.connection_status, func.count(AWSAccount.id))
            .where(AWSAccount.organization_id == organization_id)
            .group_by(AWSAccount.connection_status)
        ).all()
        counts = {status: int(count) for status, count in rows}
        total = sum(counts.values())
        connected = counts.get(AWSAccountStatus.CONNECTED, 0)
        return DashboardAccountPosture(
            total_accounts=total,
            connected_accounts=connected,
            disconnected_accounts=counts.get(AWSAccountStatus.DISCONNECTED, 0),
            accounts_requiring_attention=total - connected,
        )

    def _assets(self, organization_id: uuid.UUID) -> DashboardAssetInventory:
        active_rows = self.db.execute(
            select(Asset.is_active, func.count(Asset.id))
            .where(Asset.organization_id == organization_id)
            .group_by(Asset.is_active)
        ).all()
        active_counts = {bool(active): int(count) for active, count in active_rows}
        by_type = self._count_items(
            self.db.execute(
                select(Asset.asset_type, func.count(Asset.id))
                .where(Asset.organization_id == organization_id)
                .group_by(Asset.asset_type)
                .order_by(func.count(Asset.id).desc(), Asset.asset_type)
                .limit(DISTRIBUTION_LIMIT)
            ).all()
        )
        by_region = self._count_items(
            self.db.execute(
                select(Asset.region, func.count(Asset.id))
                .where(Asset.organization_id == organization_id)
                .group_by(Asset.region)
                .order_by(func.count(Asset.id).desc(), Asset.region)
                .limit(DISTRIBUTION_LIMIT)
            ).all()
        )
        active = active_counts.get(True, 0)
        inactive = active_counts.get(False, 0)
        return DashboardAssetInventory(
            total_assets=active + inactive,
            active_assets=active,
            inactive_assets=inactive,
            counts_by_type=by_type,
            counts_by_region=by_region,
        )

    def _findings(self, organization_id: uuid.UUID) -> DashboardFindingPosture:
        status_rows = self.db.execute(
            select(Finding.status, func.count(Finding.id))
            .where(Finding.organization_id == organization_id)
            .group_by(Finding.status)
        ).all()
        status_counts = {status: int(count) for status, count in status_rows}
        open_filter = (
            Finding.organization_id == organization_id,
            Finding.status == FindingStatus.OPEN,
        )
        severity_items = self._count_items(
            self.db.execute(
                select(Finding.severity, func.count(Finding.id))
                .where(*open_filter)
                .group_by(Finding.severity)
                .order_by(_SEVERITY_RANK.desc(), Finding.severity)
            ).all()
        )
        service_items = self._count_items(
            self.db.execute(
                select(Finding.category, func.count(Finding.id))
                .where(*open_filter)
                .group_by(Finding.category)
                .order_by(func.count(Finding.id).desc(), Finding.category)
                .limit(DISTRIBUTION_LIMIT)
            ).all()
        )
        account_items = self._count_items(
            self.db.execute(
                select(Finding.aws_account_id, func.count(Finding.id))
                .where(*open_filter)
                .group_by(Finding.aws_account_id)
                .order_by(func.count(Finding.id).desc(), Finding.aws_account_id)
                .limit(DISTRIBUTION_LIMIT)
            ).all()
        )
        recent_rows = self.db.execute(
            select(Finding, Asset.region)
            .outerjoin(Asset, Asset.id == Finding.asset_id)
            .where(
                Finding.organization_id == organization_id,
                Finding.status == FindingStatus.OPEN,
                Finding.severity.in_([FindingSeverity.CRITICAL, FindingSeverity.HIGH]),
            )
            .order_by(_SEVERITY_RANK.desc(), Finding.last_seen_at.desc(), Finding.id)
            .limit(RECENT_FINDINGS_LIMIT)
        ).all()
        return DashboardFindingPosture(
            open_total=status_counts.get(FindingStatus.OPEN, 0),
            resolved_total=status_counts.get(FindingStatus.RESOLVED, 0),
            suppressed_total=status_counts.get(FindingStatus.SUPPRESSED, 0),
            open_by_severity=severity_items,
            open_by_service=service_items,
            open_by_account=account_items,
            recent_critical_and_high_findings=[
                DashboardRecentFinding(
                    id=finding.id,
                    aws_account_id=finding.aws_account_id,
                    asset_id=finding.asset_id,
                    rule_key=finding.rule_key,
                    severity=finding.severity,
                    status=finding.status,
                    service=finding.category,
                    region=region,
                    last_seen_at=finding.last_seen_at,
                )
                for finding, region in recent_rows
            ],
        )

    def _compliance(self, organization_id: uuid.UUID) -> DashboardCompliancePosture:
        row = self.db.execute(
            select(ComplianceAssessment, ComplianceFramework)
            .join(ComplianceFramework, ComplianceFramework.id == ComplianceAssessment.framework_id)
            .where(
                ComplianceAssessment.organization_id == organization_id,
                ComplianceAssessment.status == ComplianceAssessmentStatus.COMPLETED,
            )
            .order_by(ComplianceAssessment.finished_at.desc(), ComplianceAssessment.id)
            .limit(1)
        ).first()
        if row is None:
            return DashboardCompliancePosture(
                assessment_id=None,
                framework_key=None,
                framework_name=None,
                framework_version=None,
                assessment_status=None,
                evaluation_time=None,
                controls_total=0,
                passed=0,
                failed=0,
                not_assessed=0,
                error=0,
                pass_percentage=None,
            )
        assessment, framework = row
        pass_percentage = (
            round((assessment.controls_passed / assessment.controls_total) * 100, 2)
            if assessment.controls_total
            else None
        )
        return DashboardCompliancePosture(
            assessment_id=assessment.id,
            framework_key=framework.key,
            framework_name=framework.name,
            framework_version=framework.version,
            assessment_status=assessment.status,
            evaluation_time=assessment.finished_at,
            controls_total=assessment.controls_total,
            passed=assessment.controls_passed,
            failed=assessment.controls_failed,
            not_assessed=assessment.controls_not_assessed,
            error=assessment.controls_error,
            pass_percentage=pass_percentage,
        )

    def _risk(self, organization_id: uuid.UUID) -> DashboardRiskPosture:
        assessment = self.db.scalar(
            select(RiskAssessment)
            .where(
                RiskAssessment.organization_id == organization_id,
                RiskAssessment.status == RiskAssessmentStatus.COMPLETED,
            )
            .order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id)
            .limit(1)
        )
        if assessment is None:
            return DashboardRiskPosture(
                assessment_id=None,
                evaluation_time=None,
                aggregate_score=None,
                aggregate_priority=None,
                findings_total=0,
                severity_counters=[],
                highest_risk_accounts=[],
                trend=[],
            )
        heatmap = self._account_risk_heatmap(assessment.id, organization_id)
        trend_rows = self.db.scalars(
            select(OrganizationRiskSnapshot)
            .where(OrganizationRiskSnapshot.organization_id == organization_id)
            .order_by(OrganizationRiskSnapshot.evaluation_time.desc(), OrganizationRiskSnapshot.id)
            .limit(RISK_TREND_LIMIT)
        ).all()
        return DashboardRiskPosture(
            assessment_id=assessment.id,
            evaluation_time=assessment.evaluation_time,
            aggregate_score=assessment.aggregate_score,
            aggregate_priority=assessment.aggregate_priority,
            findings_total=assessment.findings_total,
            severity_counters=[
                DashboardCountItem(key="critical", count=assessment.critical_count),
                DashboardCountItem(key="high", count=assessment.high_count),
                DashboardCountItem(key="medium", count=assessment.medium_count),
                DashboardCountItem(key="low", count=assessment.low_count),
                DashboardCountItem(key="informational", count=assessment.informational_count),
            ],
            highest_risk_accounts=heatmap[:10],
            trend=[
                DashboardRiskTrendPoint(
                    assessment_id=row.assessment_id,
                    evaluation_time=row.evaluation_time,
                    aggregate_score=row.risk_score,
                    aggregate_priority=row.priority,
                )
                for row in reversed(trend_rows)
            ],
        )

    def _account_risk_heatmap(
        self, assessment_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[DashboardAccountRiskHeatmapItem]:
        severity_rows = self.db.execute(
            select(
                AccountRiskSnapshot.aws_account_id,
                func.sum(case((Finding.severity == FindingSeverity.CRITICAL, 1), else_=0)),
                func.sum(case((Finding.severity == FindingSeverity.HIGH, 1), else_=0)),
            )
            .join(Finding, Finding.aws_account_id == AccountRiskSnapshot.aws_account_id)
            .where(
                AccountRiskSnapshot.assessment_id == assessment_id,
                AccountRiskSnapshot.organization_id == organization_id,
                Finding.organization_id == organization_id,
                Finding.status == FindingStatus.OPEN,
            )
            .group_by(AccountRiskSnapshot.aws_account_id)
        ).all()
        severity_counts = {
            account_id: (int(critical or 0), int(high or 0))
            for account_id, critical, high in severity_rows
        }
        rows = self.db.execute(
            select(AccountRiskSnapshot, AWSAccount.name, AWSAccount.account_id)
            .join(AWSAccount, AWSAccount.id == AccountRiskSnapshot.aws_account_id)
            .where(
                AccountRiskSnapshot.assessment_id == assessment_id,
                AccountRiskSnapshot.organization_id == organization_id,
            )
            .order_by(AccountRiskSnapshot.risk_score.desc(), AWSAccount.name, AWSAccount.id)
            .limit(ACCOUNT_RISK_LIMIT)
        ).all()
        return [
            DashboardAccountRiskHeatmapItem(
                aws_account_id=snapshot.aws_account_id,
                account_display_identifier=name or account_id,
                score=snapshot.risk_score,
                priority=snapshot.priority,
                findings_total=snapshot.findings_total,
                critical_count=severity_counts.get(snapshot.aws_account_id, (0, 0))[0],
                high_count=severity_counts.get(snapshot.aws_account_id, (0, 0))[1],
            )
            for snapshot, name, account_id in rows
        ]

    def _freshness(self, organization_id: uuid.UUID) -> DashboardOperationalFreshness:
        return DashboardOperationalFreshness(
            latest_completed_discovery=self._latest_discovery(organization_id, completed_only=True),
            latest_discovery=self._latest_discovery(organization_id, completed_only=False),
            latest_completed_evaluation=self._latest_evaluation(
                organization_id, completed_only=True
            ),
            latest_evaluation=self._latest_evaluation(organization_id, completed_only=False),
            latest_completed_compliance_assessment=self._latest_compliance_freshness(
                organization_id, completed_only=True
            ),
            latest_compliance_assessment=self._latest_compliance_freshness(
                organization_id, completed_only=False
            ),
            latest_completed_risk_assessment=self._latest_risk_freshness(
                organization_id, completed_only=True
            ),
            latest_risk_assessment=self._latest_risk_freshness(
                organization_id, completed_only=False
            ),
        )

    def _latest_discovery(
        self, organization_id: uuid.UUID, *, completed_only: bool
    ) -> DashboardFreshnessItem | None:
        statement = select(DiscoveryJob).where(DiscoveryJob.organization_id == organization_id)
        if completed_only:
            statement = statement.where(DiscoveryJob.status == DiscoveryJobStatus.COMPLETED)
        job = self.db.scalar(
            statement.order_by(
                DiscoveryJob.finished_at.desc(), DiscoveryJob.created_at.desc(), DiscoveryJob.id
            ).limit(1)
        )
        return (
            DashboardFreshnessItem(
                id=job.id, status=job.status, started_at=job.started_at, finished_at=job.finished_at
            )
            if job
            else None
        )

    def _latest_evaluation(
        self, organization_id: uuid.UUID, *, completed_only: bool
    ) -> DashboardFreshnessItem | None:
        statement = select(EvaluationJob).where(EvaluationJob.organization_id == organization_id)
        if completed_only:
            statement = statement.where(EvaluationJob.status == EvaluationJobStatus.COMPLETED)
        job = self.db.scalar(
            statement.order_by(
                EvaluationJob.finished_at.desc(), EvaluationJob.created_at.desc(), EvaluationJob.id
            ).limit(1)
        )
        return (
            DashboardFreshnessItem(
                id=job.id, status=job.status, started_at=job.started_at, finished_at=job.finished_at
            )
            if job
            else None
        )

    def _latest_compliance_freshness(
        self, organization_id: uuid.UUID, *, completed_only: bool
    ) -> DashboardFreshnessItem | None:
        statement = select(ComplianceAssessment).where(
            ComplianceAssessment.organization_id == organization_id
        )
        if completed_only:
            statement = statement.where(
                ComplianceAssessment.status == ComplianceAssessmentStatus.COMPLETED
            )
        assessment = self.db.scalar(
            statement.order_by(
                ComplianceAssessment.finished_at.desc(),
                ComplianceAssessment.created_at.desc(),
                ComplianceAssessment.id,
            ).limit(1)
        )
        return (
            DashboardFreshnessItem(
                id=assessment.id,
                status=assessment.status,
                started_at=assessment.started_at,
                finished_at=assessment.finished_at,
            )
            if assessment
            else None
        )

    def _latest_risk_freshness(
        self, organization_id: uuid.UUID, *, completed_only: bool
    ) -> DashboardFreshnessItem | None:
        statement = select(RiskAssessment).where(RiskAssessment.organization_id == organization_id)
        if completed_only:
            statement = statement.where(RiskAssessment.status == RiskAssessmentStatus.COMPLETED)
        assessment = self.db.scalar(
            statement.order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id).limit(1)
        )
        return (
            DashboardFreshnessItem(
                id=assessment.id,
                status=assessment.status,
                started_at=assessment.started_at,
                finished_at=assessment.finished_at,
                evaluation_time=assessment.evaluation_time,
            )
            if assessment
            else None
        )

    @staticmethod
    def _count_items(rows: Sequence[Any]) -> list[DashboardCountItem]:
        return [
            DashboardCountItem(
                key=str(key.value if hasattr(key, "value") else key), count=int(count)
            )
            for key, count in rows
        ]

    @staticmethod
    def _missing_sections(
        accounts: DashboardAccountPosture,
        assets: DashboardAssetInventory,
        findings: DashboardFindingPosture,
        compliance: DashboardCompliancePosture,
        risk: DashboardRiskPosture,
        freshness: DashboardOperationalFreshness,
    ) -> list[str]:
        missing: list[str] = []
        if accounts.total_accounts == 0:
            missing.append("accounts")
        if assets.total_assets == 0:
            missing.append("assets")
        if findings.open_total + findings.resolved_total + findings.suppressed_total == 0:
            missing.append("findings")
        if compliance.assessment_id is None:
            missing.append("latest_completed_compliance_assessment")
        if risk.assessment_id is None:
            missing.append("latest_completed_risk_assessment")
        if freshness.latest_completed_discovery is None:
            missing.append("latest_completed_discovery")
        if freshness.latest_completed_evaluation is None:
            missing.append("latest_completed_evaluation")
        return missing
