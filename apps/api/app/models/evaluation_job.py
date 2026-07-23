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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import EvaluationJobStatus, enum_values


class EvaluationJob(TimestampMixin, Base):
    __tablename__ = "evaluation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "aws_account_id",
            "organization_id",
            name="uq_evaluation_job_id_account_organization",
        ),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_evaluation_job_account_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["discovery_job_id", "aws_account_id", "organization_id"],
            [
                "discovery_jobs.id",
                "discovery_jobs.aws_account_id",
                "discovery_jobs.organization_id",
            ],
            name="fk_evaluation_job_discovery_account_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint("sequence > 0", name="evaluation_sequence_positive"),
        CheckConstraint("assets_evaluated >= 0", name="evaluation_assets_nonnegative"),
        CheckConstraint("rules_evaluated >= 0", name="evaluation_rules_nonnegative"),
        CheckConstraint("passed_count >= 0", name="evaluation_passed_nonnegative"),
        CheckConstraint("failed_count >= 0", name="evaluation_failed_nonnegative"),
        CheckConstraint("error_count >= 0", name="evaluation_error_nonnegative"),
        CheckConstraint("not_applicable_count >= 0", name="evaluation_na_nonnegative"),
        CheckConstraint("findings_created >= 0", name="evaluation_created_nonnegative"),
        CheckConstraint("findings_updated >= 0", name="evaluation_updated_nonnegative"),
        CheckConstraint("findings_resolved >= 0", name="evaluation_resolved_nonnegative"),
        CheckConstraint("findings_reopened >= 0", name="evaluation_reopened_nonnegative"),
        CheckConstraint("evaluation_errors >= 0", name="evaluation_errors_nonnegative"),
        CheckConstraint(
            "("
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'partially_completed', 'failed') "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL)"
            ")",
            name="evaluation_status_timestamps",
        ),
        Index("ix_evaluation_job_organization", "organization_id"),
        Index("ix_evaluation_job_account", "aws_account_id"),
        Index("ix_evaluation_job_status", "status"),
        Index(
            "uq_active_evaluation_job_account",
            "aws_account_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
        Index(
            "uq_evaluation_job_account_sequence",
            "aws_account_id",
            "sequence",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    discovery_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    full_evaluation: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[EvaluationJobStatus] = mapped_column(
        Enum(
            EvaluationJobStatus,
            name="evaluation_job_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=EvaluationJobStatus.PENDING,
        server_default=EvaluationJobStatus.PENDING.value,
        nullable=False,
    )
    started_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assets_evaluated: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    rules_evaluated: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    passed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    not_applicable_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings_created: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings_updated: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings_resolved: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings_reopened: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    evaluation_errors: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_summary: Mapped[str | None] = mapped_column(String(2000))
