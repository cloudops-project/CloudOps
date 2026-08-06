from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import InvitationStatus, OrganizationRole, enum_values


class OrganizationInvitation(TimestampMixin, Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        Index("ix_invitation_token_hash", "token_hash"),
        Index(
            "uq_active_invitation_org_email",
            "organization_id",
            "normalized_email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_invitation_org_status", "organization_id", "status"),
        CheckConstraint(
            "last_delivery_status IS NULL OR last_delivery_status IN "
            "('pending', 'sending', 'delivered', 'failed')",
            name="ck_invitation_delivery_status",
        ),
        CheckConstraint(
            "delivery_generation >= 0",
            name="ck_invitation_delivery_generation_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[OrganizationRole] = mapped_column(
        Enum(
            OrganizationRole,
            name="invitation_role",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(
            InvitationStatus,
            name="invitation_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=InvitationStatus.PENDING,
        server_default=InvitationStatus.PENDING.value,
        nullable=False,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sanitized delivery evidence only. Never a token, token hash, acceptance
    # URL, email body, or raw provider exception.
    last_delivery_status: Mapped[str | None] = mapped_column(String(32))
    last_delivery_error_code: Mapped[str | None] = mapped_column(String(64))
    last_delivery_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Incremented on every resend and on cancel. A provider result is applied
    #: only if this still matches the value captured before the provider call,
    #: so a slow send cannot overwrite newer state.
    delivery_generation: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
