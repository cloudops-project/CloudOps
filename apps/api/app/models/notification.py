from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZAwareDateTime
from app.models.enums import NotificationChannel, NotificationStatus, enum_values


class NotificationEvent(TimestampMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_event_type",
            "source_resource_id",
            "channel",
            "template_key",
            name="uq_notification_event_dedupe_key",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_notification_event_id_organization"
        ),
        CheckConstraint("attempt_count >= 0", name="notification_event_attempt_count_nonnegative"),
        CheckConstraint("attempt_count <= 3", name="notification_event_attempt_count_bounded"),
        CheckConstraint(
            "("
            "(status = 'pending_approval' AND approved_at IS NULL AND approved_by_user_id IS NULL "
            "AND delivered_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL "
            "AND delivered_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'delivered' AND approved_at IS NOT NULL "
            "AND delivered_at IS NOT NULL AND failed_at IS NULL) OR "
            "(status = 'failed' AND approved_at IS NOT NULL "
            "AND failed_at IS NOT NULL AND delivered_at IS NULL)"
            ")",
            name="notification_event_status_lifecycle",
        ),
        Index("ix_notification_event_organization", "organization_id"),
        Index("ix_notification_event_status", "status"),
        Index("ix_notification_event_source_resource", "source_resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            name="notification_channel",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_reference: Mapped[str | None] = mapped_column(String(320))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            name="notification_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=NotificationStatus.PENDING_APPROVAL,
        server_default=NotificationStatus.PENDING_APPROVAL.value,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    approved_delivery_fingerprint: Mapped[str | None] = mapped_column(String(64))
    scheduled_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    delivered_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    failed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    provider_key: Mapped[str | None] = mapped_column(String(50))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))


class NotificationDeliveryAttempt(TimestampMixin, Base):
    __tablename__ = "notification_delivery_attempts"
    __table_args__ = (
        UniqueConstraint(
            "notification_event_id",
            "attempt_number",
            name="uq_notification_delivery_event_attempt",
        ),
        ForeignKeyConstraint(
            ["notification_event_id", "organization_id"],
            ["notification_events.id", "notification_events.organization_id"],
            name="fk_notification_delivery_event_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "attempt_number BETWEEN 1 AND 20",
            name="notification_delivery_attempt_number",
        ),
        Index(
            "ix_notification_delivery_organization_attempted",
            "organization_id",
            "attempted_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    notification_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False)
    destination_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    response_classification: Mapped[str] = mapped_column(String(50), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    attempted_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    failed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
