from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.exceptions.errors import AppError, ConflictError, NotFoundError
from app.models import (
    AccountRiskSnapshot,
    Asset,
    AssetRiskContext,
    AWSAccount,
    CompensatingControl,
    Finding,
    FindingRiskSnapshot,
    Organization,
    OrganizationRiskSnapshot,
    RiskAssessment,
    RiskScoringPolicy,
    User,
)
from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingSeverity,
    FindingStatus,
    RiskAssessmentStatus,
    RiskCriticality,
    RiskEnvironment,
)
from app.repositories.data import Repository
from app.risk_engine import (
    POLICY_BANDS,
    POLICY_KEY,
    POLICY_VERSION,
    POLICY_WEIGHTS,
    RiskInputs,
    account_risk,
    organization_risk,
    score_finding,
)
from app.security.rbac import Capability
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService

logger = logging.getLogger(__name__)


class RiskService:
    """Persist deterministic, immutable Stage 6 risk snapshots."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_policy(self) -> RiskScoringPolicy:
        policy = self.db.scalar(
            select(RiskScoringPolicy).where(
                RiskScoringPolicy.key == POLICY_KEY,
                RiskScoringPolicy.version == POLICY_VERSION,
            )
        )
        if policy is None:
            policy = RiskScoringPolicy(
                key=POLICY_KEY,
                version=POLICY_VERSION,
                name="CloudOps deterministic risk policy v1",
                description=(
                    "CVSS-inspired deterministic cloud-risk prioritization; "
                    "this is not a CVSS score."
                ),
                weights_json=POLICY_WEIGHTS,
                bands_json=POLICY_BANDS,
                active=True,
            )
            self.db.add(policy)
            self.db.flush()
        return policy

    def assess(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        aws_account_id: uuid.UUID | None,
        evaluation_time: datetime | None = None,
    ) -> RiskAssessment:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.RISK_ASSESS
        )
        self._lock_scope(organization_id, actor.id, aws_account_id)
        policy = self.ensure_policy()
        active_filter = (
            RiskAssessment.aws_account_id.is_(None)
            if aws_account_id is None
            else RiskAssessment.aws_account_id == aws_account_id
        )
        active = self.db.scalar(
            select(RiskAssessment.id).where(
                RiskAssessment.organization_id == organization_id,
                active_filter,
                RiskAssessment.policy_id == policy.id,
                RiskAssessment.status.in_(
                    [RiskAssessmentStatus.PENDING, RiskAssessmentStatus.RUNNING]
                ),
            )
        )
        if active is not None:
            raise ConflictError(
                "risk_assessment_active",
                "An equivalent risk assessment is already active.",
            )
        assessed_at = evaluation_time or now_utc()
        started = time.perf_counter()
        assessment = RiskAssessment(
            organization_id=organization_id,
            aws_account_id=aws_account_id,
            policy_id=policy.id,
            evaluation_time=assessed_at,
            source_cutoff_at=assessed_at,
            status=RiskAssessmentStatus.RUNNING,
            started_by_user_id=actor.id,
            started_at=assessed_at,
        )
        self.db.add(assessment)
        self.db.flush()
        record_audit(
            self.db,
            "risk.assessment.requested",
            "risk_assessment",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=assessment.id,
            metadata={
                "aws_account_id": str(aws_account_id) if aws_account_id else None,
                "policy_key": policy.key,
                "policy_version": policy.version,
            },
        )
        logger.info(
            "risk.assessment.started",
            extra={
                "event_name": "risk.assessment.started",
                "organization_id": str(organization_id),
                "assessment_id": str(assessment.id),
                "policy_key": policy.key,
                "policy_version": policy.version,
            },
        )
        findings = self._active_findings(organization_id, aws_account_id)
        contexts = self._contexts(organization_id)
        controls = self._controls(organization_id, assessed_at)
        account_scores: dict[uuid.UUID, list[int]] = defaultdict(list)
        severity_counts = {severity: 0 for severity in FindingSeverity}
        for finding, asset in findings:
            context = self._context_for(contexts, finding.aws_account_id, finding.asset_id)
            control = controls.get(finding.id)
            result = score_finding(
                RiskInputs(
                    severity=finding.severity,
                    rule_key=finding.rule_key,
                    first_seen_at=finding.first_seen_at,
                    evaluation_time=assessed_at,
                    criticality=context.criticality if context else RiskCriticality.UNKNOWN,
                    environment=context.environment if context else RiskEnvironment.UNKNOWN,
                    business_impact=(
                        context.business_impact if context else BusinessImpact.UNKNOWN
                    ),
                    data_sensitivity=(
                        context.data_sensitivity if context else DataSensitivity.UNKNOWN
                    ),
                    exposure=self._asset_exposure(asset),
                    compensating_adjustment=control.score_adjustment if control else 0,
                )
            )
            self.db.add(
                FindingRiskSnapshot(
                    assessment_id=assessment.id,
                    organization_id=organization_id,
                    aws_account_id=finding.aws_account_id,
                    finding_id=finding.id,
                    asset_id=finding.asset_id,
                    source_finding_version=finding.lifecycle_version,
                    source_finding_status=finding.status,
                    policy_key=policy.key,
                    policy_version=policy.version,
                    evaluation_time=assessed_at,
                    risk_score=result.score,
                    priority=result.priority,
                    severity_points=result.components["severity"],
                    exposure_points=result.components["exposure"],
                    exploitability_points=result.components["exploitability"],
                    privilege_points=result.components["privilege"],
                    asset_criticality_points=result.components["asset_criticality"],
                    environment_points=result.components["environment"],
                    business_impact_points=result.components["business_impact"],
                    data_sensitivity_points=result.components["data_sensitivity"],
                    age_points=result.components["age"],
                    compensating_adjustment=result.components["compensating_controls"],
                    component_codes_json=dict(result.explanation_codes),
                    unknown_inputs_json=list(result.unknown_inputs),
                )
            )
            account_scores[finding.aws_account_id].append(result.score)
            severity_counts[finding.severity] += 1
            logger.info(
                "risk.finding.scored",
                extra={
                    "event_name": "risk.finding.scored",
                    "organization_id": str(organization_id),
                    "assessment_id": str(assessment.id),
                    "finding_id": str(finding.id),
                    "score": result.score,
                    "priority": result.priority.value,
                },
            )
        account_ids = self._account_ids(organization_id, aws_account_id)
        aggregate_scores: list[int] = []
        for account_id in account_ids:
            aggregate = account_risk(account_scores.get(account_id, []))
            aggregate_scores.append(aggregate.score)
            self.db.add(
                AccountRiskSnapshot(
                    assessment_id=assessment.id,
                    organization_id=organization_id,
                    aws_account_id=account_id,
                    evaluation_time=assessed_at,
                    risk_score=aggregate.score,
                    priority=aggregate.priority,
                    highest_finding_score=aggregate.highest,
                    top_ten_mean=aggregate.focused_mean,
                    all_findings_mean=aggregate.overall_mean,
                    findings_total=len(account_scores.get(account_id, [])),
                )
            )
        organization_aggregate = organization_risk(aggregate_scores)
        self.db.add(
            OrganizationRiskSnapshot(
                assessment_id=assessment.id,
                organization_id=organization_id,
                evaluation_time=assessed_at,
                risk_score=organization_aggregate.score,
                priority=organization_aggregate.priority,
                highest_account_score=organization_aggregate.highest,
                mean_account_score=organization_aggregate.focused_mean,
                accounts_total=len(account_ids),
                reason_code=organization_aggregate.reason_code,
            )
        )
        assessment.findings_total = len(findings)
        assessment.critical_count = severity_counts[FindingSeverity.CRITICAL]
        assessment.high_count = severity_counts[FindingSeverity.HIGH]
        assessment.medium_count = severity_counts[FindingSeverity.MEDIUM]
        assessment.low_count = severity_counts[FindingSeverity.LOW]
        assessment.informational_count = severity_counts[FindingSeverity.INFORMATIONAL]
        assessment.accounts_scored = len(account_ids)
        assessment.aggregate_score = organization_aggregate.score
        assessment.aggregate_priority = organization_aggregate.priority
        assessment.status = RiskAssessmentStatus.COMPLETED
        assessment.finished_at = assessed_at
        record_audit(
            self.db,
            "risk.assessment.completed",
            "risk_assessment",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=assessment.id,
            metadata={
                "score": organization_aggregate.score,
                "priority": organization_aggregate.priority.value,
                "findings_total": len(findings),
                "accounts_scored": len(account_ids),
            },
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "risk_assessment_active",
                "An equivalent risk assessment is already active.",
            ) from exc
        self.db.refresh(assessment)
        logger.info(
            "risk.assessment.completed",
            extra={
                "event_name": "risk.assessment.completed",
                "organization_id": str(organization_id),
                "assessment_id": str(assessment.id),
                "score": assessment.aggregate_score,
                "priority": (
                    assessment.aggregate_priority.value if assessment.aggregate_priority else None
                ),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return assessment

    def update_context(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        aws_account_id: uuid.UUID,
        asset_id: uuid.UUID | None,
        criticality: RiskCriticality,
        environment: RiskEnvironment,
        business_impact: BusinessImpact,
        data_sensitivity: DataSensitivity,
        expected_version: int | None,
    ) -> AssetRiskContext:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.RISK_CONTEXT_MANAGE
        )
        self._require_tenant_asset(organization_id, aws_account_id, asset_id)
        asset_filter = (
            AssetRiskContext.asset_id.is_(None)
            if asset_id is None
            else AssetRiskContext.asset_id == asset_id
        )
        context = self.db.scalar(
            select(AssetRiskContext)
            .where(
                AssetRiskContext.organization_id == organization_id,
                AssetRiskContext.aws_account_id == aws_account_id,
                asset_filter,
            )
            .with_for_update()
        )
        if context is None:
            if expected_version not in (None, 0):
                raise ConflictError("risk_context_stale", "Risk context version is stale.")
            context = AssetRiskContext(
                organization_id=organization_id,
                aws_account_id=aws_account_id,
                asset_id=asset_id,
                updated_by_user_id=actor.id,
                source="manual",
            )
            self.db.add(context)
        elif expected_version is not None and expected_version != context.version:
            raise ConflictError("risk_context_stale", "Risk context version is stale.")
        context.criticality = criticality
        context.environment = environment
        context.business_impact = business_impact
        context.data_sensitivity = data_sensitivity
        context.updated_by_user_id = actor.id
        if context.id is not None:
            context.version += 1
        self.db.flush()
        record_audit(
            self.db,
            "risk.context.changed",
            "asset_risk_context",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=context.id,
            metadata={
                "aws_account_id": str(aws_account_id),
                "asset_id": str(asset_id) if asset_id else None,
                "version": context.version,
            },
        )
        self.db.commit()
        self.db.refresh(context)
        logger.info(
            "risk.context.updated",
            extra={
                "event_name": "risk.context.updated",
                "organization_id": str(organization_id),
                "aws_account_id": str(aws_account_id),
                "asset_id": str(asset_id) if asset_id else None,
            },
        )
        return context

    def add_compensating_control(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        actor: User,
        *,
        reason: str,
        score_adjustment: int,
        expires_at: datetime | None,
    ) -> CompensatingControl:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.RISK_CONTROLS_MANAGE
        )
        finding = self.db.scalar(
            select(Finding)
            .where(
                Finding.id == finding_id,
                Finding.organization_id == organization_id,
            )
            .with_for_update()
        )
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")
        now = now_utc()
        if expires_at is not None and expires_at <= now:
            raise AppError(
                "compensating_control_expired",
                "Expiry must be later than the current time.",
                422,
            )
        active = self.db.scalar(
            select(CompensatingControl.id).where(
                CompensatingControl.finding_id == finding.id,
                CompensatingControl.active.is_(True),
            )
        )
        if active is not None:
            raise ConflictError(
                "compensating_control_active",
                "An active compensating control already exists for this finding.",
            )
        control = CompensatingControl(
            organization_id=organization_id,
            aws_account_id=finding.aws_account_id,
            finding_id=finding.id,
            reason=reason,
            score_adjustment=score_adjustment,
            created_by_user_id=actor.id,
            expires_at=expires_at,
            active=True,
        )
        self.db.add(control)
        self.db.flush()
        record_audit(
            self.db,
            "risk.compensating_control.created",
            "compensating_control",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=control.id,
            metadata={
                "finding_id": str(finding.id),
                "score_adjustment": score_adjustment,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        self.db.commit()
        self.db.refresh(control)
        logger.info(
            "risk.compensating_control.created",
            extra={
                "event_name": "risk.compensating_control.created",
                "organization_id": str(organization_id),
                "finding_id": str(finding.id),
            },
        )
        return control

    def remove_compensating_control(
        self,
        organization_id: uuid.UUID,
        control_id: uuid.UUID,
        actor: User,
    ) -> None:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.RISK_CONTROLS_MANAGE
        )
        control = self.db.scalar(
            select(CompensatingControl)
            .where(
                CompensatingControl.id == control_id,
                CompensatingControl.organization_id == organization_id,
            )
            .with_for_update()
        )
        if control is None:
            raise NotFoundError(
                "compensating_control_not_found", "Compensating control was not found."
            )
        control.active = False
        record_audit(
            self.db,
            "risk.compensating_control.removed",
            "compensating_control",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=control.id,
            metadata={"finding_id": str(control.finding_id)},
        )
        self.db.commit()
        logger.info(
            "risk.compensating_control.removed",
            extra={
                "event_name": "risk.compensating_control.removed",
                "organization_id": str(organization_id),
                "finding_id": str(control.finding_id),
            },
        )

    def _lock_scope(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        aws_account_id: uuid.UUID | None,
    ) -> None:
        try:
            if aws_account_id is not None:
                authorized = Repository(self.db).aws_account_for_user_for_update(
                    aws_account_id, actor_id, nowait=True
                )
                if authorized is None or authorized[0].organization_id != organization_id:
                    raise NotFoundError("aws_account_not_found", "AWS account was not found.")
            else:
                organization = self.db.scalar(
                    select(Organization)
                    .where(Organization.id == organization_id)
                    .with_for_update(nowait=True)
                )
                if organization is None:
                    raise NotFoundError("organization_not_found", "Organization was not found.")
        except OperationalError as exc:
            self.db.rollback()
            if getattr(exc.orig, "sqlstate", None) != "55P03":
                raise
            raise ConflictError(
                "risk_assessment_active", "A risk assessment is already active for this scope."
            ) from exc

    def _active_findings(
        self, organization_id: uuid.UUID, account_id: uuid.UUID | None
    ) -> list[tuple[Finding, Asset | None]]:
        statement = (
            select(Finding, Asset)
            .outerjoin(Asset, Finding.asset_id == Asset.id)
            .where(
                Finding.organization_id == organization_id,
                Finding.status.in_([FindingStatus.OPEN, FindingStatus.SUPPRESSED]),
            )
            .order_by(Finding.aws_account_id, Finding.id)
        )
        if account_id is not None:
            statement = statement.where(Finding.aws_account_id == account_id)
        return list(self.db.execute(statement).tuples().all())

    def _contexts(self, organization_id: uuid.UUID) -> list[AssetRiskContext]:
        return list(
            self.db.scalars(
                select(AssetRiskContext).where(AssetRiskContext.organization_id == organization_id)
            ).all()
        )

    @staticmethod
    def _context_for(
        contexts: list[AssetRiskContext],
        account_id: uuid.UUID,
        asset_id: uuid.UUID | None,
    ) -> AssetRiskContext | None:
        asset_context = next(
            (item for item in contexts if asset_id is not None and item.asset_id == asset_id),
            None,
        )
        return asset_context or next(
            (
                item
                for item in contexts
                if item.aws_account_id == account_id and item.asset_id is None
            ),
            None,
        )

    def _controls(
        self, organization_id: uuid.UUID, evaluated_at: datetime
    ) -> dict[uuid.UUID, CompensatingControl]:
        items = self.db.scalars(
            select(CompensatingControl).where(
                CompensatingControl.organization_id == organization_id,
                CompensatingControl.active.is_(True),
                or_(
                    CompensatingControl.expires_at.is_(None),
                    CompensatingControl.expires_at > evaluated_at,
                ),
            )
        ).all()
        return {item.finding_id: item for item in items}

    def _account_ids(
        self, organization_id: uuid.UUID, account_id: uuid.UUID | None
    ) -> list[uuid.UUID]:
        if account_id is not None:
            return [account_id]
        return list(
            self.db.scalars(
                select(AWSAccount.id)
                .where(AWSAccount.organization_id == organization_id)
                .order_by(AWSAccount.id)
            ).all()
        )

    def _require_tenant_asset(
        self,
        organization_id: uuid.UUID,
        account_id: uuid.UUID,
        asset_id: uuid.UUID | None,
    ) -> None:
        account = self.db.scalar(
            select(AWSAccount.id).where(
                AWSAccount.id == account_id,
                AWSAccount.organization_id == organization_id,
            )
        )
        if account is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        if asset_id is not None:
            asset = self.db.scalar(
                select(Asset.id).where(
                    Asset.id == asset_id,
                    Asset.aws_account_id == account_id,
                    Asset.organization_id == organization_id,
                )
            )
            if asset is None:
                raise NotFoundError("asset_not_found", "Asset was not found.")

    @staticmethod
    def _asset_exposure(asset: Asset | None) -> str | None:
        if asset is None:
            return None
        for key in ("publicly_accessible", "public_ip", "is_public"):
            value = asset.metadata_json.get(key)
            if value is True:
                return "public"
            if value is False:
                return "internal"
        return None
