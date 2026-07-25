from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Finding, NotificationEvent, User
from app.models.enums import (
    AuditResult,
    FindingSeverity,
    NotificationChannel,
    NotificationStatus,
)
from app.services.common import now_utc, record_audit
from app.services.notification_provider import (
    MockNotificationProvider,
    NotificationDeliveryOutcome,
    NotificationProvider,
)

MAX_DELIVERY_ATTEMPTS = 3
CRITICAL_FINDING_TEMPLATE_KEY = "critical_finding_created"
CRITICAL_FINDING_EVENT_TYPE = "security.finding.created"


def _payload_hash(organization_id: uuid.UUID, finding_id: uuid.UUID, template_key: str) -> str:
    return hashlib.sha256(
        f"{organization_id}:{finding_id}:{template_key}".encode()
    ).hexdigest()


class NotificationService:
    """Read/write operations over Stage 9 notification events.

    Delivery is synchronous and explicitly requested; no worker, queue, or
    poller exists or is created by this service. Only the deterministic mock
    provider is available in Stage 9.
    """

    def __init__(self, db: Session, provider: NotificationProvider | None = None) -> None:
        self.db = db
        self.provider = provider or MockNotificationProvider()

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
        result = self.provider.deliver(
            channel=event.channel,
            destination_reference=event.destination_reference,
            template_key=event.template_key,
            context={
                "organization_id": str(organization_id),
                "source_resource_id": str(event.source_resource_id),
            },
        )
        event.attempt_count += 1
        now: datetime = now_utc()
        if result.outcome == NotificationDeliveryOutcome.SUCCESS:
            event.status = NotificationStatus.DELIVERED
            event.delivered_at = now
            event.failed_at = None
            event.failure_reason = None
            record_audit(
                self.db,
                "notification.event.delivered",
                "notification_event",
                organization_id=organization_id,
                resource_id=event.id,
                metadata={"attempt_count": event.attempt_count},
            )
        elif event.attempt_count >= MAX_DELIVERY_ATTEMPTS:
            event.status = NotificationStatus.FAILED
            event.failed_at = now
            event.failure_reason = result.sanitized_error
            record_audit(
                self.db,
                "notification.event.failed",
                "notification_event",
                result=AuditResult.FAILED,
                organization_id=organization_id,
                resource_id=event.id,
                metadata={"attempt_count": event.attempt_count},
            )
        else:
            record_audit(
                self.db,
                "notification.event.delivery_retry",
                "notification_event",
                organization_id=organization_id,
                resource_id=event.id,
                metadata={"attempt_count": event.attempt_count},
            )
        self.db.flush()
        return event
