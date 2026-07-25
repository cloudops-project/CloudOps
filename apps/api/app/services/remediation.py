from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Finding, RemediationRequest, User
from app.models.enums import (
    AuditResult,
    FindingStatus,
    RemediationExecutionMode,
    RemediationStatus,
)
from app.security_rules import RuleRegistry, default_registry
from app.services.common import now_utc, record_audit
from app.services.remediation_executor import (
    MockRemediationExecutor,
    RemediationExecutionOutcome,
    RemediationExecutor,
)

MAX_EXECUTION_ATTEMPTS = 3


class RemediationService:
    """Read/write operations over Stage 10 remediation requests.

    Execution is synchronous and explicitly requested; no worker, queue, or
    poller exists or is created by this service. Only the deterministic mock
    executor is available in Version 1, and only for requests whose
    execution_mode is MOCK_AUTOMATION. Rule evaluation remains the sole
    authority for whether a finding exists; this service never creates,
    resolves, or reclassifies a finding.
    """

    def __init__(
        self,
        db: Session,
        executor: RemediationExecutor | None = None,
        registry: RuleRegistry = default_registry,
    ) -> None:
        self.db = db
        self.executor = executor or MockRemediationExecutor()
        self.registry = registry

    def _get_finding(self, organization_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
        finding = self.db.scalar(
            select(Finding).where(
                Finding.id == finding_id,
                Finding.organization_id == organization_id,
            )
        )
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")
        return finding

    def propose_for_finding(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        requester: User,
    ) -> RemediationRequest:
        """Deterministically generate a remediation proposal from the
        violated rule and finding metadata. If an active (not yet approved
        or already terminal) remediation request already exists for this
        finding, that existing request is returned unchanged rather than
        creating a duplicate, matching the idempotent behavior used
        elsewhere in this codebase."""
        finding = self._get_finding(organization_id, finding_id)
        if finding.status != FindingStatus.OPEN:
            raise ConflictError(
                "finding_not_open",
                "Remediation can only be proposed for an open finding.",
            )
        existing = self.db.scalar(
            select(RemediationRequest).where(
                RemediationRequest.finding_id == finding_id,
                RemediationRequest.status.in_(
                    (RemediationStatus.PENDING_APPROVAL, RemediationStatus.APPROVED)
                ),
            )
        )
        if existing is not None:
            return existing

        rule = self.registry.get(finding.rule_key)
        rule_name = rule.name if rule else finding.rule_key
        rule_description = rule.description if rule else "Rule details are unavailable."
        rule_remediation = (
            rule.remediation if rule else "Review the finding evidence and remediate manually."
        )
        rule_version = rule.version if rule else finding.rule_version

        candidate = RemediationRequest(
            organization_id=organization_id,
            aws_account_id=finding.aws_account_id,
            finding_id=finding.id,
            rule_key=finding.rule_key,
            rule_version=rule_version,
            requested_by_user_id=requester.id,
            execution_mode=RemediationExecutionMode.MOCK_AUTOMATION,
            automation_eligible=True,
            title=f"Remediate {rule_name}",
            summary=rule_description,
            remediation_steps_json=[rule_remediation],
            verification_steps_json=[
                "Re-run discovery and evaluation for the affected AWS account.",
                f"Confirm rule {finding.rule_key} no longer produces this finding.",
            ],
            rollback_steps_json=[
                "Mock automation makes no AWS changes in Version 1; no rollback is required.",
                "If a manual change was made outside this workflow, revert it using your "
                "organization's standard change-management process.",
            ],
        )
        try:
            with self.db.begin_nested():
                self.db.add(candidate)
                self.db.flush()
        except IntegrityError:
            existing_after_race = self.db.scalar(
                select(RemediationRequest).where(
                    RemediationRequest.finding_id == finding_id,
                    RemediationRequest.status.in_(
                        (RemediationStatus.PENDING_APPROVAL, RemediationStatus.APPROVED)
                    ),
                )
            )
            if existing_after_race is not None:
                return existing_after_race
            raise
        record_audit(
            self.db,
            "remediation.request.proposed",
            "remediation_request",
            organization_id=organization_id,
            actor_user_id=requester.id,
            resource_id=candidate.id,
            metadata={"finding_id": str(finding_id), "rule_key": finding.rule_key},
        )
        return candidate

    def _get_scoped(
        self, organization_id: uuid.UUID, request_id: uuid.UUID
    ) -> RemediationRequest:
        request = self.db.scalar(
            select(RemediationRequest).where(
                RemediationRequest.id == request_id,
                RemediationRequest.organization_id == organization_id,
            )
        )
        if request is None:
            raise NotFoundError(
                "remediation_request_not_found", "Remediation request was not found."
            )
        return request

    def approve(
        self, organization_id: uuid.UUID, request_id: uuid.UUID, approver: User
    ) -> RemediationRequest:
        request = self._get_scoped(organization_id, request_id)
        if request.status == RemediationStatus.APPROVED:
            return request
        if request.status != RemediationStatus.PENDING_APPROVAL:
            raise ConflictError(
                "remediation_invalid_transition",
                f"Cannot approve a remediation request in status '{request.status.value}'.",
            )
        request.status = RemediationStatus.APPROVED
        request.approved_at = now_utc()
        request.approved_by_user_id = approver.id
        self.db.flush()
        record_audit(
            self.db,
            "remediation.request.approved",
            "remediation_request",
            organization_id=organization_id,
            actor_user_id=approver.id,
            resource_id=request.id,
        )
        return request

    def reject(
        self,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        rejector: User,
        reason: str,
    ) -> RemediationRequest:
        request = self._get_scoped(organization_id, request_id)
        if request.status == RemediationStatus.REJECTED:
            return request
        if request.status != RemediationStatus.PENDING_APPROVAL:
            raise ConflictError(
                "remediation_invalid_transition",
                f"Cannot reject a remediation request in status '{request.status.value}'.",
            )
        request.status = RemediationStatus.REJECTED
        request.rejected_at = now_utc()
        request.rejected_by_user_id = rejector.id
        request.rejection_reason = reason
        self.db.flush()
        record_audit(
            self.db,
            "remediation.request.rejected",
            "remediation_request",
            organization_id=organization_id,
            actor_user_id=rejector.id,
            resource_id=request.id,
            metadata={"reason": reason},
        )
        return request

    def cancel(
        self, organization_id: uuid.UUID, request_id: uuid.UUID, actor: User
    ) -> RemediationRequest:
        request = self._get_scoped(organization_id, request_id)
        if request.status == RemediationStatus.CANCELLED:
            return request
        if request.status not in (
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
        ):
            raise ConflictError(
                "remediation_invalid_transition",
                f"Cannot cancel a remediation request in status '{request.status.value}'.",
            )
        request.status = RemediationStatus.CANCELLED
        request.cancelled_at = now_utc()
        self.db.flush()
        record_audit(
            self.db,
            "remediation.request.cancelled",
            "remediation_request",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=request.id,
        )
        return request

    def execute(
        self, organization_id: uuid.UUID, request_id: uuid.UUID
    ) -> RemediationRequest:
        """Attempt mock execution of an APPROVED remediation request exactly
        once per call. A retryable failure leaves the request APPROVED with
        an incremented attempt_count; the third failed attempt transitions
        the request to FAILED. Only MOCK_AUTOMATION requests are
        executable; MANUAL and JIRA_DRAFT requests are informational only
        and are rejected here."""
        request = self._get_scoped(organization_id, request_id)
        if request.status != RemediationStatus.APPROVED:
            raise ConflictError(
                "remediation_invalid_transition",
                f"Cannot execute a remediation request in status '{request.status.value}'.",
            )
        if request.execution_mode != RemediationExecutionMode.MOCK_AUTOMATION:
            raise ConflictError(
                "remediation_not_automatable",
                "Only mock_automation requests can be executed in Version 1.",
            )
        result = self.executor.execute(
            rule_key=request.rule_key,
            finding_id=request.finding_id,
            context={
                "organization_id": str(organization_id),
                "aws_account_id": str(request.aws_account_id),
            },
        )
        request.attempt_count += 1
        request.before_state_json = result.before_state
        now = now_utc()
        if result.outcome == RemediationExecutionOutcome.SUCCESS:
            request.status = RemediationStatus.SUCCEEDED
            request.executed_at = now
            request.after_state_json = result.after_state
            request.execution_result_json = {
                "outcome": "success",
                "attempt_count": request.attempt_count,
            }
            request.failure_reason = None
            record_audit(
                self.db,
                "remediation.request.succeeded",
                "remediation_request",
                organization_id=organization_id,
                resource_id=request.id,
                metadata={"attempt_count": request.attempt_count},
            )
        elif request.attempt_count >= MAX_EXECUTION_ATTEMPTS:
            request.status = RemediationStatus.FAILED
            request.failed_at = now
            request.failure_reason = result.sanitized_error
            request.execution_result_json = {
                "outcome": "failed",
                "attempt_count": request.attempt_count,
            }
            record_audit(
                self.db,
                "remediation.request.failed",
                "remediation_request",
                result=AuditResult.FAILED,
                organization_id=organization_id,
                resource_id=request.id,
                metadata={"attempt_count": request.attempt_count},
            )
        else:
            record_audit(
                self.db,
                "remediation.request.execution_retry",
                "remediation_request",
                organization_id=organization_id,
                resource_id=request.id,
                metadata={"attempt_count": request.attempt_count},
            )
        self.db.flush()
        return request
