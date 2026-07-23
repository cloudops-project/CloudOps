from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import AWSAccountStatus, enum_values


class AWSAccount(TimestampMixin, Base):
    __tablename__ = "aws_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "account_id", name="uq_aws_account_org_account"),
        UniqueConstraint("organization_id", "role_arn", name="uq_aws_account_org_role_arn"),
        UniqueConstraint("external_id", name="uq_aws_account_external_id"),
        UniqueConstraint("id", "organization_id", name="uq_aws_account_id_organization"),
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
