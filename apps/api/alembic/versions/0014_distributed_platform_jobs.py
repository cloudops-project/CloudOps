"""Add durable distributed platform jobs and scheduler occurrence evidence.

Revision ID: 0014_distributed_platform_jobs
Revises: 0013_demo_notification_delivery
Create Date: 2026-07-27 04:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0014_distributed_platform_jobs"
down_revision: str | None = "0013_demo_notification_delivery"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

JOB_TYPES = (
    "discovery",
    "evaluation",
    "compliance",
    "risk_recalculation",
    "notification_delivery",
    "scheduled_scan",
    "remediation_simulation",
)
JOB_STATUSES = (
    "available",
    "leased",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    "dead_lettered",
    "cancelled",
)


def upgrade() -> None:
    op.add_column(
        "scan_schedules",
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "platform_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "job_type",
            sa.Enum(
                *JOB_TYPES,
                name="platform_job_type",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                *JOB_STATUSES,
                name="platform_job_status",
                native_enum=False,
                length=24,
            ),
            server_default="available",
            nullable=False,
        ),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("payload_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_summary", sa.String(500), nullable=True),
        sa.Column("result_reference", sa.String(255), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_platform_jobs_platform_job_attempt_nonnegative",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 20", name="ck_platform_jobs_platform_job_max_attempts"
        ),
        sa.CheckConstraint(
            "priority BETWEEN -100 AND 100", name="ck_platform_jobs_platform_job_priority"
        ),
        sa.CheckConstraint(
            "(status IN ('leased', 'running') AND lease_token IS NOT NULL "
            "AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status NOT IN ('leased', 'running') AND lease_token IS NULL "
            "AND worker_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_platform_jobs_platform_job_lease_state",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_platform_jobs_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_platform_jobs"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_platform_job_id_organization"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "job_type",
            "idempotency_key",
            name="uq_platform_job_tenant_idempotency",
        ),
    )
    op.create_foreign_key(
        "fk_platform_job_parent_organization",
        "platform_jobs",
        "platform_jobs",
        ["parent_job_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_platform_job_acquisition",
        "platform_jobs",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_platform_job_organization_status",
        "platform_jobs",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_platform_job_correlation", "platform_jobs", ["correlation_id"]
    )
    op.create_index(
        "uq_platform_job_active_reference",
        "platform_jobs",
        ["organization_id", "job_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('available', 'leased', 'running', 'retry_wait')"
        ),
        sqlite_where=sa.text(
            "status IN ('available', 'leased', 'running', 'retry_wait')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_platform_job_active_reference", table_name="platform_jobs")
    op.drop_index("ix_platform_job_correlation", table_name="platform_jobs")
    op.drop_index("ix_platform_job_organization_status", table_name="platform_jobs")
    op.drop_index("ix_platform_job_acquisition", table_name="platform_jobs")
    op.drop_table("platform_jobs")
    op.drop_column("scan_schedules", "last_enqueued_at")
