"""Create Stage 11 scheduler foundation persistence.

Revision ID: 0012_stage11_scheduler
Revises: 0011_stage10_remediation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_stage11_scheduler"
down_revision: str | None = "0011_stage10_remediation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("created_by_user_id", sa.Uuid()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_scan_schedule_account_organization",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "interval_minutes >= 15", name="scan_schedule_interval_minimum"
        ),
    )
    op.create_index("ix_scan_schedule_organization", "scan_schedules", ["organization_id"])
    op.create_index("ix_scan_schedule_account", "scan_schedules", ["aws_account_id"])
    op.create_index("ix_scan_schedule_next_run", "scan_schedules", ["next_run_at"])

    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid()),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column(
            "status", sa.String(16), server_default="pending", nullable=False
        ),
        sa.Column("discovery_job_id", sa.Uuid()),
        sa.Column("evaluation_job_id", sa.Uuid()),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["scan_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["discovery_job_id"], ["discovery_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_job_id"], ["evaluation_jobs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_scan_run_account_organization",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "("
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)"
            ")",
            name="scan_run_status_lifecycle",
        ),
    )
    op.create_index("ix_scan_run_organization", "scan_runs", ["organization_id"])
    op.create_index("ix_scan_run_account", "scan_runs", ["aws_account_id"])
    op.create_index("ix_scan_run_schedule", "scan_runs", ["schedule_id"])
    op.create_index("ix_scan_run_status", "scan_runs", ["status"])
    op.create_index(
        "uq_scan_run_active_per_account",
        "scan_runs",
        ["aws_account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
        sqlite_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_scan_run_active_per_account", table_name="scan_runs")
    op.drop_index("ix_scan_run_status", table_name="scan_runs")
    op.drop_index("ix_scan_run_schedule", table_name="scan_runs")
    op.drop_index("ix_scan_run_account", table_name="scan_runs")
    op.drop_index("ix_scan_run_organization", table_name="scan_runs")
    op.drop_table("scan_runs")
    op.drop_index("ix_scan_schedule_next_run", table_name="scan_schedules")
    op.drop_index("ix_scan_schedule_account", table_name="scan_schedules")
    op.drop_index("ix_scan_schedule_organization", table_name="scan_schedules")
    op.drop_table("scan_schedules")
