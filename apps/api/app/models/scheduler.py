from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZAwareDateTime
from app.models.enums import ScanRunStatus, ScanRunTrigger, enum_values

MINIMUM_INTERVAL_MINUTES = 15


class ScanSchedule(TimestampMixin, Base):
    """A recurring discovery+evaluation cadence for one AWS account. The
    scheduler foundation never mutates AWS resources; it only starts the
    existing read-only discovery and deterministic evaluation pipelines on
    the account's own permission boundary, exactly as the manual "run
    evaluation" flow already does."""

    __tablename__ = "scan_schedules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_scan_schedule_account_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"interval_minutes >= {MINIMUM_INTERVAL_MINUTES}",
            name="scan_schedule_interval_minimum",
        ),
        Index("ix_scan_schedule_organization", "organization_id"),
        Index("ix_scan_schedule_account", "aws_account_id"),
        Index("ix_scan_schedule_next_run", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    last_enqueued_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    next_run_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())


class ScanRun(TimestampMixin, Base):
    """One execution record of a schedule (or a manual run-now). Overlap
    protection is enforced at the database level: only one pending or
    running scan may exist per AWS account at a time."""

    __tablename__ = "scan_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_scan_run_account_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "("
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)"
            ")",
            name="scan_run_status_lifecycle",
        ),
        Index("ix_scan_run_organization", "organization_id"),
        Index("ix_scan_run_account", "aws_account_id"),
        Index("ix_scan_run_schedule", "schedule_id"),
        Index("ix_scan_run_status", "status"),
        Index(
            "uq_scan_run_active_per_account",
            "aws_account_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("scan_schedules.id", ondelete="SET NULL")
    )
    trigger: Mapped[ScanRunTrigger] = mapped_column(
        Enum(
            ScanRunTrigger,
            name="scan_run_trigger",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    status: Mapped[ScanRunStatus] = mapped_column(
        Enum(
            ScanRunStatus,
            name="scan_run_status",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=enum_values,
        ),
        default=ScanRunStatus.PENDING,
        server_default=ScanRunStatus.PENDING.value,
        nullable=False,
    )
    discovery_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("discovery_jobs.id", ondelete="SET NULL")
    )
    evaluation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluation_jobs.id", ondelete="SET NULL")
    )
    error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
