from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Asset, AWSAccount, EvaluationJob, EvaluationRuleResult, Finding, User
from app.models.enums import (
    AuditResult,
    AWSAccountStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    RuleResultStatus,
)
from app.repositories.findings import EvaluationJobRepository, FindingRepository
from app.security.rbac import Capability
from app.security_rules import RuleRegistry, default_registry
from app.security_rules.base import RuleContext, SecurityRule
from app.security_rules.results import RuleResult, sanitize_evidence
from app.services.common import now_utc, record_audit
from app.services.notifications import NotificationService
from app.services.organizations import OrganizationService

logger = logging.getLogger("cloudops.security")


class EvaluationService:
    def __init__(self, db: Session, registry: RuleRegistry = default_registry) -> None:
        self.db = db
        self.registry = registry
        self.jobs = EvaluationJobRepository(db)
        self.findings = FindingRepository(db)

    def start(
        self,
        account_id: uuid.UUID,
        actor: User,
        *,
        discovery_job_id: uuid.UUID | None = None,
    ) -> EvaluationJob:
        account = self.db.scalar(
            select(AWSAccount).where(AWSAccount.id == account_id).with_for_update()
        )
        if account is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        OrganizationService(self.db).require_capability(
            account.organization_id, actor.id, Capability.EVALUATIONS_START
        )
        if account.connection_status != AWSAccountStatus.CONNECTED:
            raise ConflictError(
                "aws_account_not_connected", "Only connected AWS accounts can be evaluated."
            )
        if self.jobs.active_for_account(account.id):
            raise ConflictError(
                "evaluation_already_running", "An evaluation is already active for this account."
            )
        job = EvaluationJob(
            organization_id=account.organization_id,
            aws_account_id=account.id,
            discovery_job_id=discovery_job_id,
            sequence=self.jobs.next_sequence(account.id),
            started_by_user_id=actor.id,
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "evaluation_already_running", "An evaluation is already active for this account."
            ) from exc
        return self.run(job.id, actor)

    def run(self, job_id: uuid.UUID, actor: User) -> EvaluationJob:
        job = self.db.scalar(
            select(EvaluationJob)
            .where(EvaluationJob.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if job is None:
            raise NotFoundError("evaluation_not_found", "Evaluation was not found.")
        if job.status != EvaluationJobStatus.PENDING:
            raise ConflictError("evaluation_not_pending", "Only pending evaluations can run.")
        job.status = EvaluationJobStatus.RUNNING
        job.started_at = now_utc()
        record_audit(
            self.db,
            "security.evaluation.started",
            "evaluation_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            metadata={"aws_account_id": str(job.aws_account_id), "sequence": job.sequence},
        )
        self.db.commit()
        logger.info(
            "security.evaluation.started",
            extra={
                "event_name": "security.evaluation.started",
                "organization_id": str(job.organization_id),
                "aws_account_id": str(job.aws_account_id),
                "evaluation_job_id": str(job.id),
            },
        )
        started = time.perf_counter()
        try:
            assets = tuple(
                self.db.scalars(
                    select(Asset)
                    .where(
                        Asset.aws_account_id == job.aws_account_id,
                        Asset.organization_id == job.organization_id,
                        Asset.is_active.is_(True),
                    )
                    .order_by(Asset.id)
                )
            )
            context = RuleContext(assets, evaluated_at=now_utc())
            job.assets_evaluated = len(assets)
            errors: list[str] = []
            for rule in self.registry.filter(enabled=True):
                rule_summary = EvaluationRuleResult(
                    evaluation_job_id=job.id,
                    organization_id=job.organization_id,
                    aws_account_id=job.aws_account_id,
                    rule_key=rule.key,
                    rule_version=rule.version,
                    passed_count=0,
                    failed_count=0,
                    not_applicable_count=0,
                    error_count=0,
                )
                self.db.add(rule_summary)
                targets: tuple[Asset | None, ...] = (
                    (None,)
                    if rule.asset_type is None
                    else tuple(asset for asset in assets if rule.applies_to(asset))
                )
                for asset in targets:
                    try:
                        result = rule.evaluate(asset, context)
                    except Exception:
                        result = RuleResult(RuleResultStatus.ERROR, {}, "rule_execution_failed")
                    self._apply_result(job, rule, asset, result, rule_summary)
                    if result.status == RuleResultStatus.ERROR:
                        errors.append(f"{rule.key}:{result.error_code or 'rule_error'}")
                        logger.warning(
                            "security.evaluation.rule_error",
                            extra={
                                "event_name": "security.evaluation.rule_error",
                                "organization_id": str(job.organization_id),
                                "aws_account_id": str(job.aws_account_id),
                                "evaluation_job_id": str(job.id),
                                "asset_id": str(asset.id) if asset else None,
                                "rule_key": rule.key,
                                "result": "error",
                                "error_code": result.error_code or "rule_error",
                            },
                        )
            terminal = (
                EvaluationJobStatus.FAILED
                if job.rules_evaluated > 0 and job.evaluation_errors == job.rules_evaluated
                else (
                    EvaluationJobStatus.PARTIALLY_COMPLETED
                    if errors
                    else EvaluationJobStatus.COMPLETED
                )
            )
            return self._finish(
                job.id,
                actor,
                terminal,
                errors,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception:
            self.db.rollback()
            return self._recover_failed(
                job_id,
                actor,
                "evaluation_execution_failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    def _apply_result(
        self,
        job: EvaluationJob,
        rule: SecurityRule,
        asset: Asset | None,
        result: RuleResult,
        rule_summary: EvaluationRuleResult | None = None,
    ) -> None:
        job.rules_evaluated += 1
        if result.status == RuleResultStatus.PASSED:
            job.passed_count += 1
            if rule_summary is not None:
                rule_summary.passed_count += 1
        elif result.status == RuleResultStatus.FAILED:
            job.failed_count += 1
            if rule_summary is not None:
                rule_summary.failed_count += 1
        elif result.status == RuleResultStatus.ERROR:
            job.error_count += 1
            job.evaluation_errors += 1
            if rule_summary is not None:
                rule_summary.error_count += 1
        else:
            job.not_applicable_count += 1
            if rule_summary is not None:
                rule_summary.not_applicable_count += 1
        finding = self.findings.for_rule(job.aws_account_id, rule.key, asset.id if asset else None)
        if finding is not None:
            last_job = self.db.get(EvaluationJob, finding.last_evaluation_id)
            if last_job is not None and last_job.sequence > job.sequence:
                return
        if result.status == RuleResultStatus.ERROR:
            return
        now = now_utc()
        if result.status == RuleResultStatus.FAILED:
            created = False
            if finding is None:
                candidate = Finding(
                    organization_id=job.organization_id,
                    aws_account_id=job.aws_account_id,
                    asset_id=asset.id if asset else None,
                    rule_key=rule.key,
                    rule_version=rule.version,
                    severity=rule.severity,
                    category=rule.category,
                    evidence_json=sanitize_evidence(result.evidence),
                    first_seen_at=now,
                    last_seen_at=now,
                    last_evaluation_id=job.id,
                )
                try:
                    with self.db.begin_nested():
                        self.db.add(candidate)
                        self.db.flush()
                    finding = candidate
                    job.findings_created += 1
                    event = "security.finding.created"
                    previous_status = None
                    created = True
                except IntegrityError:
                    finding = self.findings.for_rule(
                        job.aws_account_id, rule.key, asset.id if asset else None
                    )
                    if finding is None:
                        raise
            if not created:
                assert finding is not None
                was_resolved = finding.status == FindingStatus.RESOLVED
                was_suppressed = finding.status == FindingStatus.SUPPRESSED
                previous_status = finding.status.value
                active_suppression = finding.status == FindingStatus.SUPPRESSED and (
                    finding.suppressed_until is None
                    or _timezone_safe(finding.suppressed_until) > now
                )
                if not active_suppression:
                    finding.status = FindingStatus.OPEN
                    finding.suppressed_at = None
                    finding.suppressed_until = None
                    finding.suppression_reason = None
                    finding.suppressed_by_user_id = None
                finding.resolved_at = None
                finding.last_seen_at = now
                finding.evidence_json = sanitize_evidence(result.evidence)
                finding.rule_version = rule.version
                finding.last_evaluation_id = job.id
                finding.lifecycle_version += 1
                if was_resolved or (was_suppressed and not active_suppression):
                    job.findings_reopened += 1
                    event = "security.finding.reopened"
                else:
                    job.findings_updated += 1
                    event = "security.finding.updated"
            record_audit(
                self.db,
                event,
                "finding",
                organization_id=job.organization_id,
                actor_user_id=job.started_by_user_id,
                resource_id=finding.id,
                metadata={"rule_key": rule.key, "asset_id": str(asset.id) if asset else None},
            )
            if created and finding.severity == FindingSeverity.CRITICAL:
                NotificationService(self.db).create_for_critical_finding(finding)
            self._log_finding(
                event,
                finding,
                job=job,
                rule_key=rule.key,
                previous_status=previous_status,
            )
        elif result.status == RuleResultStatus.PASSED and finding is not None:
            active_suppression = finding.status == FindingStatus.SUPPRESSED and (
                finding.suppressed_until is None or _timezone_safe(finding.suppressed_until) > now
            )
            if active_suppression:
                self.db.flush()
                return
            if finding.status != FindingStatus.RESOLVED:
                previous_status = finding.status.value
                finding.status = FindingStatus.RESOLVED
                finding.resolved_at = now
                finding.suppressed_at = None
                finding.suppressed_until = None
                finding.suppression_reason = None
                finding.suppressed_by_user_id = None
                finding.last_evaluation_id = job.id
                finding.lifecycle_version += 1
                job.findings_resolved += 1
                record_audit(
                    self.db,
                    "security.finding.resolved",
                    "finding",
                    organization_id=job.organization_id,
                    actor_user_id=job.started_by_user_id,
                    resource_id=finding.id,
                    metadata={"rule_key": rule.key},
                )
                self._log_finding(
                    "security.finding.resolved",
                    finding,
                    job=job,
                    rule_key=rule.key,
                    previous_status=previous_status,
                )
        self.db.flush()

    def _finish(
        self,
        job_id: uuid.UUID,
        actor: User,
        status: EvaluationJobStatus,
        errors: list[str],
        *,
        duration_ms: int = 0,
    ) -> EvaluationJob:
        job = self.db.scalar(
            select(EvaluationJob)
            .where(EvaluationJob.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if job is None:
            raise NotFoundError("evaluation_not_found", "Evaluation was not found.")
        if job.status != EvaluationJobStatus.RUNNING:
            raise ConflictError("evaluation_not_running", "Only running evaluations can finish.")
        job.status = status
        job.finished_at = now_utc()
        job.error_summary = "; ".join(errors)[:2000] or None
        event = {
            EvaluationJobStatus.COMPLETED: "security.evaluation.completed",
            EvaluationJobStatus.PARTIALLY_COMPLETED: "security.evaluation.partially_completed",
            EvaluationJobStatus.FAILED: "security.evaluation.failed",
        }[status]
        record_audit(
            self.db,
            event,
            "evaluation_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            result=(
                AuditResult.FAILED
                if status == EvaluationJobStatus.FAILED
                else AuditResult.SUCCEEDED
            ),
            metadata={
                "aws_account_id": str(job.aws_account_id),
                "rules_evaluated": job.rules_evaluated,
                "failed_count": job.failed_count,
                "error_count": job.error_count,
                "findings_created": job.findings_created,
                "findings_updated": job.findings_updated,
                "findings_resolved": job.findings_resolved,
                "findings_reopened": job.findings_reopened,
                "evaluation_errors": job.evaluation_errors,
            },
        )
        self.db.commit()
        self.db.refresh(job)
        logger.info(
            event,
            extra={
                "event_name": event,
                "organization_id": str(job.organization_id),
                "aws_account_id": str(job.aws_account_id),
                "evaluation_job_id": str(job.id),
                "result": status.value,
                "assets_evaluated": job.assets_evaluated,
                "rules_evaluated": job.rules_evaluated,
                "findings_created": job.findings_created,
                "findings_updated": job.findings_updated,
                "findings_resolved": job.findings_resolved,
                "findings_reopened": job.findings_reopened,
                "evaluation_errors": job.evaluation_errors,
                "duration_ms": duration_ms,
            },
        )
        return job

    def _recover_failed(
        self,
        job_id: uuid.UUID,
        actor: User,
        error_code: str,
        *,
        duration_ms: int,
    ) -> EvaluationJob:
        try:
            return self._finish(
                job_id,
                actor,
                EvaluationJobStatus.FAILED,
                [error_code],
                duration_ms=duration_ms,
            )
        except Exception:
            self.db.rollback()
            job = self.db.scalar(
                select(EvaluationJob).where(EvaluationJob.id == job_id).with_for_update()
            )
            if job is None:
                raise NotFoundError("evaluation_not_found", "Evaluation was not found.") from None
            if job.status == EvaluationJobStatus.RUNNING:
                job.status = EvaluationJobStatus.FAILED
                job.finished_at = now_utc()
                job.error_summary = error_code
                self.db.commit()
                self.db.refresh(job)
            logger.error(
                "security.evaluation.failed",
                extra={
                    "event_name": "security.evaluation.failed",
                    "organization_id": str(job.organization_id),
                    "aws_account_id": str(job.aws_account_id),
                    "evaluation_job_id": str(job.id),
                    "result": EvaluationJobStatus.FAILED.value,
                    "error_code": error_code,
                    "duration_ms": duration_ms,
                },
            )
            return job

    @staticmethod
    def _log_finding(
        event: str,
        finding: Finding,
        *,
        job: EvaluationJob | None,
        rule_key: str,
        previous_status: str | None,
    ) -> None:
        logger.info(
            event,
            extra={
                "event_name": event,
                "organization_id": str(finding.organization_id),
                "aws_account_id": str(finding.aws_account_id),
                "evaluation_job_id": str(job.id) if job else None,
                "finding_id": str(finding.id),
                "asset_id": str(finding.asset_id) if finding.asset_id else None,
                "rule_key": rule_key,
                "previous_status": previous_status,
                "new_status": finding.status.value,
            },
        )

    def suppress(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        actor: User,
        reason: str,
        until: datetime | None,
    ) -> Finding:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.FINDINGS_SUPPRESS
        )
        finding = self.findings.get(organization_id, finding_id)
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")
        if until is not None and _timezone_safe(until) <= now_utc():
            raise ConflictError(
                "invalid_suppression_expiry",
                "Suppression expiry must be in the future.",
            )
        previous_status = finding.status.value
        finding.status = FindingStatus.SUPPRESSED
        finding.resolved_at = None
        finding.suppressed_at = now_utc()
        finding.suppressed_until = until
        finding.suppression_reason = reason.strip()
        finding.suppressed_by_user_id = actor.id
        finding.lifecycle_version += 1
        record_audit(
            self.db,
            "security.finding.suppressed",
            "finding",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=finding.id,
            metadata={"reason": reason.strip()[:200]},
        )
        self.db.commit()
        self.db.refresh(finding)
        self._log_finding(
            "security.finding.suppressed",
            finding,
            job=None,
            rule_key=finding.rule_key,
            previous_status=previous_status,
        )
        return finding

    def unsuppress(self, organization_id: uuid.UUID, finding_id: uuid.UUID, actor: User) -> Finding:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.FINDINGS_SUPPRESS
        )
        finding = self.findings.get(organization_id, finding_id)
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")
        if finding.status == FindingStatus.SUPPRESSED:
            previous_status = finding.status.value
            finding.status = FindingStatus.OPEN
            finding.suppressed_at = None
            finding.suppressed_until = None
            finding.suppression_reason = None
            finding.suppressed_by_user_id = None
            finding.lifecycle_version += 1
            record_audit(
                self.db,
                "security.finding.unsuppressed",
                "finding",
                organization_id=organization_id,
                actor_user_id=actor.id,
                resource_id=finding.id,
            )
            self.db.commit()
            self.db.refresh(finding)
            self._log_finding(
                "security.finding.unsuppressed",
                finding,
                job=None,
                rule_key=finding.rule_key,
                previous_status=previous_status,
            )
        return finding


def _timezone_safe(value: datetime) -> datetime:
    if value.tzinfo is None:
        from datetime import UTC

        return value.replace(tzinfo=UTC)
    return value
