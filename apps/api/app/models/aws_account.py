from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZAwareDateTime
from app.models.enums import AWSAccountStatus, enum_values


class AWSAccount(TimestampMixin, Base):
    __tablename__ = "aws_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "account_id", name="uq_aws_account_org_account"),
        UniqueConstraint("organization_id", "role_arn", name="uq_aws_account_org_role_arn"),
        UniqueConstraint("external_id", name="uq_aws_account_external_id"),
        UniqueConstraint(
            "remediation_external_id",
            name="uq_aws_account_remediation_external_id",
        ),
        UniqueConstraint("id", "organization_id", name="uq_aws_account_id_organization"),
        ForeignKeyConstraint(
            ["organization_id", "sandbox_approved_by_user_id"],
            ["organization_members.organization_id", "organization_members.user_id"],
            name="fk_aws_account_sandbox_approver_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(sandbox_approved = false AND sandbox_approved_at IS NULL "
            "AND sandbox_approved_by_user_id IS NULL) OR "
            "(sandbox_approved = true AND sandbox_approved_at IS NOT NULL "
            "AND sandbox_approved_by_user_id IS NOT NULL)",
            name="aws_account_sandbox_approval_complete",
        ),
        Index("ix_aws_account_organization", "organization_id"),
        Index("ix_aws_account_status", "status"),
        Index("ix_aws_account_connection_status", "connection_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    role_arn: Mapped[str | None] = mapped_column(String(2048))
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    remediation_role_arn: Mapped[str | None] = mapped_column(String(2048))
    remediation_external_id: Mapped[str | None] = mapped_column(String(128))
    sandbox_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    sandbox_approved_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    sandbox_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[AWSAccountStatus] = mapped_column(
        Enum(
            AWSAccountStatus,
            name="aws_account_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=AWSAccountStatus.PENDING,
        server_default=AWSAccountStatus.PENDING.value,
        nullable=False,
    )
    connection_status: Mapped[AWSAccountStatus] = mapped_column(
        Enum(
            AWSAccountStatus,
            name="aws_connection_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=AWSAccountStatus.PENDING,
        server_default=AWSAccountStatus.PENDING.value,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    validation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
