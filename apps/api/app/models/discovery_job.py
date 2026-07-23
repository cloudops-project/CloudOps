from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import DiscoveryJobStatus, enum_values


class DiscoveryJob(TimestampMixin, Base):
    __tablename__ = "discovery_jobs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "aws_account_id",
            "organization_id",
            name="uq_discovery_job_id_account_organization",
        ),
        Index("ix_discovery_job_organization", "organization_id"),
        Index("ix_discovery_job_account", "aws_account_id"),
        Index("ix_discovery_job_status", "status"),
        Index(
            "uq_active_discovery_job_account",
            "aws_account_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
        CheckConstraint("assets_discovered >= 0", name="discovery_assets_discovered_nonnegative"),
        CheckConstraint("assets_created >= 0", name="discovery_assets_created_nonnegative"),
        CheckConstraint("assets_updated >= 0", name="discovery_assets_updated_nonnegative"),
        CheckConstraint("assets_deactivated >= 0", name="discovery_assets_deactivated_nonnegative"),
        CheckConstraint(
            "("
            "(status = 'pending' AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND (error_summary IS NULL OR error_summary = '')) OR "
            "(status = 'partially_completed' AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL) OR "
            "(status = 'failed' AND started_at IS NOT NULL AND finished_at IS NOT NULL)"
            ")",
            name="discovery_status_timestamps",
        ),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_discovery_job_account_organization",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[DiscoveryJobStatus] = mapped_column(
        Enum(
            DiscoveryJobStatus,
            name="discovery_job_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=DiscoveryJobStatus.PENDING,
        server_default="pending",
        nullable=False,
    )
    started_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assets_discovered: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    assets_created: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    assets_updated: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    assets_deactivated: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_summary: Mapped[str | None] = mapped_column(String(2000))
