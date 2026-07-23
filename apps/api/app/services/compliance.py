from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.exceptions.errors import ConflictError, NotFoundError
from app.models import (
    ComplianceAssessment,
    ComplianceAssessmentControl,
    ComplianceControl,
    ComplianceFramework,
    EvaluationJob,
    EvaluationRuleResult,
    Finding,
    RuleControlMapping,
    User,
)
from app.models.enums import (
    ComplianceAssessmentStatus,
    ComplianceControlStatus,
    EvaluationJobStatus,
    FindingStatus,
)
from app.repositories.data import Repository
from app.security.rbac import Capability
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService

logger = logging.getLogger(__name__)

CATALOG: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "cis_aws",
        "CIS AWS Foundations",
        "1.5",
        "CloudOps summary for network exposure safeguards.",
        "https://www.cisecurity.org/benchmark/amazon_web_services",
        "4.1",
    ),
    (
        "nist_csf",
        "NIST Cybersecurity Framework",
        "2.0",
        "CloudOps summary for protective controls.",
        "https://www.nist.gov/cyberframework",
        "PR.AA-01",
    ),
    (
        "iso_27001",
        "ISO/IEC 27001",
        "2022",
        "CloudOps summary for access and network controls.",
        "https://www.iso.org/standard/27001",
        "A.8.20",
    ),
    (
        "pci_dss",
        "PCI DSS",
        "4.0",
        "CloudOps summary for access restriction controls.",
        "https://www.pcisecuritystandards.org/",
        "1.2.1",
    ),
)
MAPPED_RULES = (
    "EC2_SG_SSH_OPEN_TO_WORLD",
    "EC2_SG_RDP_OPEN_TO_WORLD",
    "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
)


class ComplianceService:
    """Build immutable control snapshots from persisted Stage 4 evaluation output."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_catalog(self) -> None:
        for key, name, version, description, reference, control_key in CATALOG:
            framework = self.db.scalar(
                select(ComplianceFramework).where(
                    ComplianceFramework.key == key,
                    ComplianceFramework.version == version,
                )
            )
            if framework is None:
                framework = ComplianceFramework(
                    key=key,
                    name=name,
                    version=version,
                    description=description,
                    official_reference=reference,
                )
                self.db.add(framework)
                self.db.flush()
            control = self.db.scalar(
                select(ComplianceControl).where(
                    ComplianceControl.framework_id == framework.id,
                    ComplianceControl.control_key == control_key,
                )
            )
            if control is None:
                control = ComplianceControl(
                    framework_id=framework.id,
                    control_key=control_key,
                    title=f"CloudOps mapping: {control_key}",
                    description=description,
                    section="CloudOps mapping",
                )
                self.db.add(control)
                self.db.flush()
            for rule_key in MAPPED_RULES:
                exists = self.db.scalar(
                    select(RuleControlMapping.id).where(
                        RuleControlMapping.rule_key == rule_key,
                        RuleControlMapping.control_id == control.id,
                        RuleControlMapping.minimum_rule_version == 1,
                        RuleControlMapping.maximum_rule_version.is_(None),
                    )
                )
                if exists is None:
                    self.db.add(
                        RuleControlMapping(
                            rule_key=rule_key,
                            minimum_rule_version=1,
                            framework_id=framework.id,
                            control_id=control.id,
                            rationale="CloudOps deterministic network-exposure mapping.",
                        )
                    )
        self.db.flush()

    def framework(self, key: str, version: str | None = None) -> ComplianceFramework:
        statement = select(ComplianceFramework).where(
            ComplianceFramework.key == key,
            ComplianceFramework.enabled.is_(True),
        )
        if version:
            statement = statement.where(ComplianceFramework.version == version)
        framework = self.db.scalar(statement.order_by(ComplianceFramework.version.desc()))
        if framework is None:
            raise NotFoundError("framework_not_found", "Compliance framework was not found.")
        return framework

    def assess(
        self,
        account_id: uuid.UUID,
        actor: User,
        framework_key: str,
        version: str | None,
        evaluation_job_id: uuid.UUID | None,
    ) -> ComplianceAssessment:
        try:
            authorized = Repository(self.db).aws_account_for_user_for_update(
                account_id, actor.id, nowait=True
            )
        except OperationalError as exc:
            self.db.rollback()
            if getattr(exc.orig, "sqlstate", None) != "55P03":
                raise
            raise ConflictError(
                "compliance_assessment_active",
                "A compliance assessment is already active for this account and framework.",
            ) from exc
        if authorized is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        account, _membership = authorized
        OrganizationService(self.db).require_capability(
            account.organization_id, actor.id, Capability.COMPLIANCE_ASSESS
        )
        self.ensure_catalog()
        framework = self.framework(framework_key, version)
        active = self.db.scalar(
            select(ComplianceAssessment.id).where(
                ComplianceAssessment.aws_account_id == account.id,
                ComplianceAssessment.framework_id == framework.id,
                ComplianceAssessment.status.in_(
                    [
                        ComplianceAssessmentStatus.PENDING,
                        ComplianceAssessmentStatus.RUNNING,
                    ]
                ),
            )
        )
        if active is not None:
            raise ConflictError(
                "compliance_assessment_active",
                "A compliance assessment is already active for this account and framework.",
            )
        evaluation, source_state = self._source_evaluation(
            account.id, account.organization_id, evaluation_job_id
        )
        now = now_utc()
        assessment = ComplianceAssessment(
            organization_id=account.organization_id,
            aws_account_id=account.id,
            framework_id=framework.id,
            evaluation_job_id=evaluation.id if evaluation else None,
            status=ComplianceAssessmentStatus.RUNNING,
            started_at=now,
        )
        self.db.add(assessment)
        self.db.flush()
        record_audit(
            self.db,
            "compliance.assessment.started",
            "compliance_assessment",
            organization_id=account.organization_id,
            actor_user_id=actor.id,
            resource_id=assessment.id,
            metadata={
                "framework": framework.key,
                "framework_version": framework.version,
                "aws_account_id": str(account.id),
            },
        )
        logger.info(
            "compliance.assessment.started",
            extra={
                "event_name": "compliance.assessment.started",
                "organization_id": str(account.organization_id),
                "assessment_id": str(assessment.id),
            },
        )
        started = time.perf_counter()
        controls = list(
            self.db.scalars(
                select(ComplianceControl)
                .where(ComplianceControl.framework_id == framework.id)
                .order_by(ComplianceControl.control_key)
            ).all()
        )
        mapping_by_control: dict[uuid.UUID, list[RuleControlMapping]] = {
            control.id: [] for control in controls
        }
        mappings = self.db.scalars(
            select(RuleControlMapping).where(RuleControlMapping.framework_id == framework.id)
        ).all()
        for mapping in mappings:
            mapping_by_control[mapping.control_id].append(mapping)
        findings = list(
            self.db.scalars(
                select(Finding).where(
                    Finding.organization_id == account.organization_id,
                    Finding.aws_account_id == account.id,
                )
            ).all()
        )
        rule_results = (
            list(
                self.db.scalars(
                    select(EvaluationRuleResult).where(
                        EvaluationRuleResult.evaluation_job_id == evaluation.id,
                        EvaluationRuleResult.organization_id == account.organization_id,
                        EvaluationRuleResult.aws_account_id == account.id,
                    )
                ).all()
            )
            if evaluation is not None
            else []
        )

        failed = 0
        passed = 0
        not_assessed = 0
        errors = 0
        for control in controls:
            relevant = self._relevant_findings(findings, mapping_by_control[control.id])
            control_status = self._control_status(
                mappings=mapping_by_control[control.id],
                findings=relevant,
                source_state=source_state,
                rule_results=rule_results,
            )
            if control_status == ComplianceControlStatus.FAIL:
                failed += 1
            elif control_status == ComplianceControlStatus.PASS:
                passed += 1
            elif control_status == ComplianceControlStatus.ERROR:
                errors += 1
            else:
                not_assessed += 1
            self.db.add(
                ComplianceAssessmentControl(
                    assessment_id=assessment.id,
                    control_id=control.id,
                    framework_id=framework.id,
                    status=control_status,
                    findings_count=len(relevant),
                    assessed_at=now,
                )
            )
            logger.info(
                f"compliance.control.{_log_control_status(control_status)}",
                extra={
                    "event_name": f"compliance.control.{_log_control_status(control_status)}",
                    "organization_id": str(account.organization_id),
                    "assessment_id": str(assessment.id),
                },
            )
        assessment.controls_total = len(controls)
        assessment.controls_passed = passed
        assessment.controls_failed = failed
        assessment.controls_not_assessed = not_assessed
        assessment.controls_error = errors
        assessment.findings_count = len(findings)
        assessment.status = ComplianceAssessmentStatus.COMPLETED
        assessment.finished_at = now
        record_audit(
            self.db,
            "compliance.assessment.completed",
            "compliance_assessment",
            organization_id=account.organization_id,
            actor_user_id=actor.id,
            resource_id=assessment.id,
            metadata={
                "framework": framework.key,
                "failed": failed,
                "not_assessed": not_assessed,
                "errors": errors,
                "evaluation_id": str(evaluation.id) if evaluation else None,
            },
        )
        self.db.commit()
        self.db.refresh(assessment)
        logger.info(
            "compliance.assessment.completed",
            extra={
                "event_name": "compliance.assessment.completed",
                "organization_id": str(account.organization_id),
                "assessment_id": str(assessment.id),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return assessment

    def controls(self, framework: ComplianceFramework) -> list[ComplianceControl]:
        return list(
            self.db.scalars(
                select(ComplianceControl)
                .where(ComplianceControl.framework_id == framework.id)
                .order_by(ComplianceControl.control_key)
            ).all()
        )

    def _source_evaluation(
        self,
        account_id: uuid.UUID,
        organization_id: uuid.UUID,
        evaluation_job_id: uuid.UUID | None,
    ) -> tuple[EvaluationJob | None, ComplianceControlStatus]:
        statement = select(EvaluationJob).where(
            EvaluationJob.aws_account_id == account_id,
            EvaluationJob.organization_id == organization_id,
        )
        if evaluation_job_id is not None:
            evaluation = self.db.scalar(statement.where(EvaluationJob.id == evaluation_job_id))
        else:
            evaluation = self.db.scalar(
                statement.order_by(EvaluationJob.finished_at.desc(), EvaluationJob.id)
            )
        if evaluation is None:
            return None, ComplianceControlStatus.NOT_ASSESSED
        if (
            evaluation.status == EvaluationJobStatus.COMPLETED
            and evaluation.error_count == 0
            and evaluation.evaluation_errors == 0
        ):
            return evaluation, ComplianceControlStatus.PASS
        if evaluation.status in {
            EvaluationJobStatus.COMPLETED,
            EvaluationJobStatus.PARTIALLY_COMPLETED,
            EvaluationJobStatus.FAILED,
        } and (evaluation.error_count > 0 or evaluation.evaluation_errors > 0):
            return evaluation, ComplianceControlStatus.ERROR
        return evaluation, ComplianceControlStatus.NOT_ASSESSED

    @staticmethod
    def _relevant_findings(
        findings: list[Finding], mappings: list[RuleControlMapping]
    ) -> list[Finding]:
        return [
            finding
            for finding in findings
            if any(
                mapping.rule_key == finding.rule_key
                and finding.rule_version >= mapping.minimum_rule_version
                and (
                    mapping.maximum_rule_version is None
                    or finding.rule_version <= mapping.maximum_rule_version
                )
                for mapping in mappings
            )
        ]

    @staticmethod
    def _control_status(
        *,
        mappings: list[RuleControlMapping],
        findings: list[Finding],
        source_state: ComplianceControlStatus,
        rule_results: list[EvaluationRuleResult],
    ) -> ComplianceControlStatus:
        """Evaluate overlapping mapping ranges as a deterministic union per rule key."""
        if not mappings:
            return ComplianceControlStatus.NOT_ASSESSED
        active_finding_statuses = {FindingStatus.OPEN, FindingStatus.SUPPRESSED}
        has_failing_finding = any(finding.status in active_finding_statuses for finding in findings)
        if has_failing_finding:
            return ComplianceControlStatus.FAIL
        if source_state != ComplianceControlStatus.PASS:
            return source_state
        matched_results: list[EvaluationRuleResult] = []
        for rule_key in sorted({mapping.rule_key for mapping in mappings}):
            ranges = [mapping for mapping in mappings if mapping.rule_key == rule_key]
            matches = [
                result
                for result in rule_results
                if result.rule_key == rule_key
                and any(
                    result.rule_version >= mapping.minimum_rule_version
                    and (
                        mapping.maximum_rule_version is None
                        or result.rule_version <= mapping.maximum_rule_version
                    )
                    for mapping in ranges
                )
            ]
            if not matches:
                return ComplianceControlStatus.NOT_ASSESSED
            for result in matches:
                if result not in matched_results:
                    matched_results.append(result)
        if any(result.error_count > 0 for result in matched_results):
            return ComplianceControlStatus.ERROR
        if any(result.failed_count > 0 for result in matched_results):
            return ComplianceControlStatus.ERROR
        if any(
            result.passed_count + result.failed_count + result.not_applicable_count == 0
            for result in matched_results
        ):
            return ComplianceControlStatus.NOT_ASSESSED
        if all(result.passed_count == 0 for result in matched_results):
            return ComplianceControlStatus.NOT_ASSESSED
        return ComplianceControlStatus.PASS


def _log_control_status(status: ComplianceControlStatus) -> str:
    return {
        ComplianceControlStatus.PASS: "passed",
        ComplianceControlStatus.FAIL: "failed",
        ComplianceControlStatus.NOT_ASSESSED: "not_assessed",
        ComplianceControlStatus.ERROR: "error",
    }[status]
