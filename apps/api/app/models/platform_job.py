from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
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

from app.db.base import Base, TimestampMixin, TZAwareDateTime
from app.models.enums import PlatformJobStatus, PlatformJobType, enum_values


class PlatformJob(TimestampMixin, Base):
    """PostgreSQL is the durable source of truth; payloads contain references only."""

    __tablename__ = "platform_jobs"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_platform_job_id_organization"),
        UniqueConstraint(
            "organization_id",
            "job_type",
            "idempotency_key",
            name="uq_platform_job_tenant_idempotency",
        ),
        ForeignKeyConstraint(
            ["parent_job_id", "organization_id"],
            ["platform_jobs.id", "platform_jobs.organization_id"],
            name="fk_platform_job_parent_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_count >= 0", name="platform_job_attempt_nonnegative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 20", name="platform_job_max_attempts"),
        CheckConstraint("priority BETWEEN -100 AND 100", name="platform_job_priority"),
        CheckConstraint(
            "(status IN ('leased', 'running') AND lease_token IS NOT NULL "
            "AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status NOT IN ('leased', 'running') AND lease_token IS NULL "
            "AND worker_id IS NULL AND lease_expires_at IS NULL)",
            name="platform_job_lease_state",
        ),
        Index(
            "ix_platform_job_acquisition",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index("ix_platform_job_organization_status", "organization_id", "status"),
        Index("ix_platform_job_correlation", "correlation_id"),
        Index(
            "uq_platform_job_active_reference",
            "organization_id",
            "job_type",
            "reference_id",
            unique=True,
            postgresql_where=text(
                "status IN ('available', 'leased', 'running', 'retry_wait')"
            ),
            sqlite_where=text(
                "status IN ('available', 'leased', 'running', 'retry_wait')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[PlatformJobType] = mapped_column(
        Enum(
            PlatformJobType,
            name="platform_job_type",
            native_enum=False,
            create_constraint=True,
            length=40,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    status: Mapped[PlatformJobStatus] = mapped_column(
        Enum(
            PlatformJobStatus,
            name="platform_job_status",
            native_enum=False,
            create_constraint=True,
            length=24,
            values_callable=enum_values,
        ),
        default=PlatformJobStatus.AVAILABLE,
        server_default=PlatformJobStatus.AVAILABLE.value,
        nullable=False,
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    available_at: Mapped[datetime] = mapped_column(TZAwareDateTime(), nullable=False)
    leased_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_generation: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    failed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    dead_lettered_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_summary: Mapped[str | None] = mapped_column(String(500))
    result_reference: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, default=uuid.uuid4)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
