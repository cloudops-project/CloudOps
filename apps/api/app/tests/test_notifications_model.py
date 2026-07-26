from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NotificationEvent
from app.models.enums import NotificationChannel, NotificationStatus
from app.tests.test_risk import _finding, _tenant


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_notification_event_defaults_to_pending_approval(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user)
    db.commit()

    event = NotificationEvent(
        organization_id=organization.id,
        source_event_type="security.finding.created",
        source_resource_type="finding",
        source_resource_id=finding.id,
        channel=NotificationChannel.EMAIL,
        template_key="critical_finding_created",
        payload_hash=_hash(str(finding.id)),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    assert event.status == NotificationStatus.PENDING_APPROVAL
    assert event.attempt_count == 0
    assert event.destination_reference is None
    assert event.approved_by_user_id is None
    assert event.approved_at is None
    assert event.delivered_at is None
    assert event.failed_at is None
    assert event.failure_reason is None
    assert event.created_at is not None
    assert event.updated_at is not None


def test_notification_event_records_full_approved_and_delivered_lifecycle(
    db: Session,
) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user)
    db.commit()

    now = datetime.now(UTC)
    event = NotificationEvent(
        organization_id=organization.id,
        source_event_type="security.finding.created",
        source_resource_type="finding",
        source_resource_id=finding.id,
        channel=NotificationChannel.EMAIL,
        template_key="critical_finding_created",
        payload_hash=_hash(str(finding.id)),
        status=NotificationStatus.DELIVERED,
        attempt_count=1,
        approved_by_user_id=user.id,
        approved_at=now,
        delivered_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    stored = db.scalar(select(NotificationEvent).where(NotificationEvent.id == event.id))
    assert stored is not None
    assert stored.status == NotificationStatus.DELIVERED
    assert stored.approved_by_user_id == user.id
    assert stored.delivered_at is not None
    assert stored.failed_at is None


def test_notification_event_id_is_a_real_uuid(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _ = _finding(db, organization, account, user)
    db.commit()

    event = NotificationEvent(
        organization_id=organization.id,
        source_event_type="security.finding.created",
        source_resource_type="finding",
        source_resource_id=finding.id,
        channel=NotificationChannel.EMAIL,
        template_key="critical_finding_created",
        payload_hash=_hash(str(finding.id)),
    )
    db.add(event)
    db.commit()

    assert isinstance(event.id, uuid.UUID)
