from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import (
    AWSAccount,
    EvaluationJob,
    Finding,
    NotificationDeliveryAttempt,
    NotificationEvent,
    Organization,
    OrganizationMembership,
    PlatformJob,
    User,
)
from app.models.enums import (
    AuditResult,
    FindingSeverity,
    MembershipStatus,
    NotificationChannel,
    NotificationStatus,
    OrganizationRole,
    PlatformJobType,
    UserStatus,
)
from app.services.common import now_utc, record_audit
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
    NotificationProvider,
    notification_provider_from_settings,
)
from app.services.platform_jobs import PlatformJobService

logger = logging.getLogger("cloudops.notifications")

MAX_DELIVERY_ATTEMPTS = 3
CRITICAL_FINDING_TEMPLATE_KEY = "critical_finding_created"
CRITICAL_FINDING_EVENT_TYPE = "security.finding.created"
CRITICAL_FINDING_TEMPLATE_VERSION = 1
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _payload_hash(organization_id: uuid.UUID, finding_id: uuid.UUID, template_key: str) -> str:
    return hashlib.sha256(f"{organization_id}:{finding_id}:{template_key}".encode()).hexdigest()


class NotificationService:
    """Read/write operations over Stage 9 notification events.

    Delivery is synchronous and explicitly requested; no worker, queue, or
    poller exists or is created by this service. The deterministic mock
    provider remains the default; the SMTP provider is available for the local
    Mailpit demo path when configured.
    """

    def __init__(self, db: Session, provider: NotificationProvider | None = None) -> None:
        self.db = db
        self.provider = provider or notification_provider_from_settings(get_settings())
        self.last_result: NotificationDeliveryResult | None = None

    def create_for_critical_finding(self, finding: Finding) -> NotificationEvent | None:
        """Create a PENDING_APPROVAL notification event for a newly created
        CRITICAL finding. Callers must invoke this only when a finding row
        was just created (not for reopened, updated, or pre-existing
        findings); creation-novelty is the caller's responsibility, matching
        the surrounding evaluation service's existing created/updated
        branching. Severity is defensively re-checked here rather than
        trusted solely from the caller.

        Returns None if finding.severity is not CRITICAL, or if an identical
        event already exists (idempotent no-op via the database dedupe
        constraint); otherwise returns the created event.
        """
        if finding.severity != FindingSeverity.CRITICAL:
            return None
        candidate = NotificationEvent(
            organization_id=finding.organization_id,
            source_event_type=CRITICAL_FINDING_EVENT_TYPE,
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key=CRITICAL_FINDING_TEMPLATE_KEY,
            destination_reference=None,
            payload_hash=_payload_hash(
                finding.organization_id, finding.id, CRITICAL_FINDING_TEMPLATE_KEY
            ),
        )
        try:
            with self.db.begin_nested():
                self.db.add(candidate)
                self.db.flush()
        except IntegrityError:
            return None
        record_audit(
            self.db,
            "notification.event.created",
            "notification_event",
            organization_id=finding.organization_id,
            resource_id=candidate.id,
            metadata={"finding_id": str(finding.id), "template_key": CRITICAL_FINDING_TEMPLATE_KEY},
        )
        return candidate

    def _get_scoped(self, organization_id: uuid.UUID, event_id: uuid.UUID) -> NotificationEvent:
        event = self.db.scalar(
            select(NotificationEvent).where(
                NotificationEvent.id == event_id,
                NotificationEvent.organization_id == organization_id,
            )
        )
        if event is None:
            raise NotFoundError("notification_event_not_found", "Notification event was not found.")
        return event

    def _recipients_for_event(self, event: NotificationEvent) -> list[str]:
        recipients: list[str] = []
        admin_rows = self.db.execute(
            select(User.email)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .where(
                OrganizationMembership.organization_id == event.organization_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                OrganizationMembership.role.in_([OrganizationRole.OWNER, OrganizationRole.ADMIN]),
                User.status == UserStatus.ACTIVE,
            )
            .order_by(User.normalized_email)
        ).all()
        recipients.extend(str(row[0]) for row in admin_rows)

        finding = self.db.get(Finding, event.source_resource_id)
        if finding is not None and finding.organization_id == event.organization_id:
            evaluation = self.db.get(EvaluationJob, finding.last_evaluation_id)
            if evaluation is not None and evaluation.organization_id == event.organization_id:
                actor = self.db.get(User, evaluation.started_by_user_id)
                if actor is not None and actor.status == UserStatus.ACTIVE:
                    recipients.append(actor.email)

        deduped: list[str] = []
        seen: set[str] = set()
        for recipient in recipients:
            email = recipient.strip()
            normalized = email.casefold()
            if not EMAIL_RE.match(email):
                raise ConflictError(
                    "notification_invalid_recipient",
                    "Notification has no valid email recipients.",
                )
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(email)
        if not deduped:
            raise ConflictError(
                "notification_invalid_recipient",
                "Notification has no valid email recipients.",
            )
        return deduped

    def _email_content(self, event: NotificationEvent) -> tuple[str, str]:
        organization = self.db.get(Organization, event.organization_id)
        finding = self.db.get(Finding, event.source_resource_id)
        account = None
        evaluation = None
        if finding is not None and finding.organization_id == event.organization_id:
            account = self.db.get(AWSAccount, finding.aws_account_id)
            evaluation = self.db.get(EvaluationJob, finding.last_evaluation_id)
        org_name = organization.name if organization is not None else "CloudOps organization"
        account_name = account.name if account is not None else "AWS account"
        account_id = account.account_id if account is not None else None
        masked_account = (
            f"********{account_id[-4:]}" if account_id and len(account_id) >= 4 else "unknown"
        )
        safe_org_name = re.sub(r"[\r\n\x00-\x1f]", " ", org_name).strip()[:200]
        subject = f"CloudOps security notification for {safe_org_name}"[:998]
        evaluation_time = event.created_at
        if evaluation is not None and evaluation.finished_at is not None:
            evaluation_time = evaluation.finished_at
        lines = [
            f"Organization: {org_name}",
            f"AWS account: {account_name} ({masked_account})",
            f"Scan/evaluation time: {evaluation_time}",
            "Notification type: critical security finding",
            f"Finding count: {evaluation.findings_created if evaluation else 1}",
            "Critical/high/medium/low summary: critical=1, high=0, medium=0, low=0",
            "Compliance summary: review the CloudOps compliance page for the latest assessment.",
            "Risk summary: review the CloudOps risk page for the latest deterministic risk score.",
        ]
        if finding is not None:
            lines.extend(
                [
                    "Top finding:",
                    f"- {finding.rule_key} ({finding.severity.value})",
                ]
            )
        lines.extend(
            [
                "",
                "Remediation execution is simulated in CloudOps Version 1.",
                (
                    "Review the finding, compliance, risk, remediation, schedule, and audit "
                    "pages before action."
                ),
                f"Open CloudOps: {get_settings().frontend_url}",
            ]
        )
        return subject, "\n".join(lines)

    def approve(
        self, organization_id: uuid.UUID, event_id: uuid.UUID, approver: User
    ) -> NotificationEvent:
        event = self._get_scoped(organization_id, event_id)
        if event.status == NotificationStatus.APPROVED:
            return event
        if event.status != NotificationStatus.PENDING_APPROVAL:
            raise ConflictError(
                "notification_event_invalid_transition",
                f"Cannot approve a notification event in status '{event.status.value}'.",
            )
        event.status = NotificationStatus.APPROVED
        event.approved_at = now_utc()
        event.approved_by_user_id = approver.id
        event.approved_delivery_fingerprint = self._delivery_fingerprint(event)
        self.db.flush()
        record_audit(
            self.db,
            "notification.event.approved",
            "notification_event",
            organization_id=organization_id,
            actor_user_id=approver.id,
            resource_id=event.id,
        )
        return event

    def revoke_approval(
        self, organization_id: uuid.UUID, event_id: uuid.UUID, actor: User
    ) -> NotificationEvent:
        event = self._get_scoped(organization_id, event_id)
        if event.status == NotificationStatus.PENDING_APPROVAL:
            return event
        if event.status != NotificationStatus.APPROVED:
            raise ConflictError(
                "notification_event_invalid_transition",
                "Only an approved notification can have approval revoked.",
            )
        event.status = NotificationStatus.PENDING_APPROVAL
        event.approved_at = None
        event.approved_by_user_id = None
        event.approved_delivery_fingerprint = None
        event.scheduled_at = None
        record_audit(
            self.db,
            "notification.event.approval_revoked",
            "notification_event",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=event.id,
        )
        self.db.flush()
        return event

    def deliver(self, organization_id: uuid.UUID, event_id: uuid.UUID) -> NotificationEvent:
        """Attempt delivery of an APPROVED notification event exactly once
        per call. A retryable failure leaves the event APPROVED with an
        incremented attempt_count; the third failed attempt transitions the
        event to FAILED. The provider is never invoked for a DELIVERED or
        FAILED event, and never invoked for a PENDING_APPROVAL event."""
        event = self._get_scoped(organization_id, event_id)
        if event.status != NotificationStatus.APPROVED:
            raise ConflictError(
                "notification_event_invalid_transition",
                f"Cannot deliver a notification event in status '{event.status.value}'.",
            )
        if event.approved_delivery_fingerprint != self._delivery_fingerprint(event):
            raise ConflictError(
                "notification_approval_stale",
                "Notification content, destination, template, or provider changed after approval.",
            )
        subject, text_body = self._email_content(event)
        provider_started = time.perf_counter()
        result = self.provider.deliver(
            channel=event.channel,
            destination_reference=event.destination_reference,
            recipients=self._recipients_for_event(event),
            subject=subject,
            text_body=text_body,
            template_key=event.template_key,
            context={
                "organization_id": str(organization_id),
                "source_resource_id": str(event.source_resource_id),
            },
        )
        logger.info(
            "notification.provider.completed",
            extra={
                "provider_key": self.provider.key,
                "result": result.outcome.value,
                "duration_ms": round(
                    (time.perf_counter() - provider_started) * 1000,
                    2,
                ),
                "error_code": result.error_code,
                "retryable": result.retryable,
            },
        )
        self.last_result = result
        event.attempt_count += 1
        now: datetime = now_utc()
        content_hash = hashlib.sha256(
            f"{subject}\n{text_body}".encode()
        ).hexdigest()
        evidence = NotificationDeliveryAttempt(
            organization_id=organization_id,
            notification_event_id=event.id,
            attempt_number=event.attempt_count,
            provider_key=self.provider.key,
            destination_reference=f"recipient_count:{len(self._recipients_for_event(event))}",
            template_key=event.template_key,
            template_version=CRITICAL_FINDING_TEMPLATE_VERSION,
            content_hash=content_hash,
            provider_message_id=result.provider_message_id,
            response_classification=(
                "success"
                if result.outcome == NotificationDeliveryOutcome.SUCCESS
                else ("retryable_failure" if result.retryable else "permanent_failure")
            ),
            error_code=result.error_code,
            error_summary=result.sanitized_error,
            attempted_at=now,
            delivered_at=(
                now if result.outcome == NotificationDeliveryOutcome.SUCCESS else None
            ),
            failed_at=(
                now if result.outcome == NotificationDeliveryOutcome.FAILURE else None
            ),
        )
        self.db.add(evidence)
        if result.outcome == NotificationDeliveryOutcome.SUCCESS:
            event.status = NotificationStatus.DELIVERED
            event.delivered_at = now
            event.failed_at = None
            event.failure_reason = None
            event.provider_key = self.provider.key
            event.provider_message_id = result.provider_message_id
            record_audit(
                self.db,
                "notification.event.delivered",
                "notification_event",
                organization_id=organization_id,
                resource_id=event.id,
                metadata={
                    "attempt_count": event.attempt_count,
                    "provider_key": self.provider.key,
                    "provider_message_id": result.provider_message_id,
                },
            )
        elif not result.retryable or event.attempt_count >= MAX_DELIVERY_ATTEMPTS:
            event.status = NotificationStatus.FAILED
            event.failed_at = now
            event.failure_reason = result.sanitized_error
            event.provider_key = self.provider.key
            record_audit(
                self.db,
                "notification.event.failed",
                "notification_event",
                result=AuditResult.FAILED,
                organization_id=organization_id,
                resource_id=event.id,
                metadata={"attempt_count": event.attempt_count, "provider_key": self.provider.key},
            )
        else:
            event.provider_key = self.provider.key
            record_audit(
                self.db,
                "notification.event.delivery_retry",
                "notification_event",
                organization_id=organization_id,
                resource_id=event.id,
                metadata={"attempt_count": event.attempt_count, "provider_key": self.provider.key},
            )
        self.db.flush()
        return event

    def enqueue_delivery(
        self, organization_id: uuid.UUID, event_id: uuid.UUID, actor: User
    ) -> PlatformJob:

        event = self._get_scoped(organization_id, event_id)
        if event.status != NotificationStatus.APPROVED:
            raise ConflictError(
                "notification_event_invalid_transition",
                "Only an approved notification can be queued for delivery.",
            )
        job, _created = PlatformJobService(self.db).enqueue(
            organization_id=organization_id,
            job_type=PlatformJobType.NOTIFICATION_DELIVERY,
            reference_id=event.id,
            idempotency_key=(
                f"notification-delivery:{event.id}:"
                f"{event.approved_delivery_fingerprint or 'missing'}"
            ),
            payload={"notification_event_id": str(event.id)},
            actor_user_id=actor.id,
        )
        event.scheduled_at = now_utc()
        self.db.flush()
        return job

    def _delivery_fingerprint(self, event: NotificationEvent) -> str:
        value = ":".join(
            (
                event.channel.value,
                event.template_key,
                event.destination_reference or "",
                event.payload_hash,
                self.provider.key,
            )
        )
        return hashlib.sha256(value.encode()).hexdigest()
