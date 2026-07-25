"""Create Stage 10 remediation workflow persistence.

Revision ID: 0011_stage10_remediation
Revises: 0010_stage9_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_stage10_remediation"
down_revision: str | None = "0010_stage9_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "remediation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(160), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid()),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("rejected_by_user_id", sa.Uuid()),
        sa.Column(
            "status",
            sa.String(32),
            server_default="pending_approval",
            nullable=False,
        ),
        sa.Column(
            "execution_mode",
            sa.String(32),
            server_default="mock_automation",
            nullable=False,
        ),
        sa.Column(
            "automation_eligible",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "remediation_steps_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "verification_steps_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            "rollback_steps_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("before_state_json", sa.JSON()),
        sa.Column("after_state_json", sa.JSON()),
        sa.Column("execution_result_json", sa.JSON()),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejection_reason", sa.String(1000)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_remediation_finding_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="remediation_attempt_count_nonnegative"
        ),
        sa.CheckConstraint(
            "attempt_count <= 3", name="remediation_attempt_count_bounded"
        ),
        sa.CheckConstraint(
            "("
            "(status = 'pending_approval' AND approved_at IS NULL AND rejected_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL AND rejected_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'rejected' AND rejected_at IS NOT NULL AND approved_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND rejected_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'succeeded' AND approved_at IS NOT NULL AND executed_at IS NOT NULL "
            "AND rejected_at IS NULL AND cancelled_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'failed' AND approved_at IS NOT NULL AND failed_at IS NOT NULL "
            "AND rejected_at IS NULL AND cancelled_at IS NULL AND executed_at IS NULL)"
            ")",
            name="remediation_status_lifecycle",
        ),
    )
    op.create_index("ix_remediation_organization", "remediation_requests", ["organization_id"])
    op.create_index("ix_remediation_finding", "remediation_requests", ["finding_id"])
    op.create_index("ix_remediation_status", "remediation_requests", ["status"])
    op.create_index(
        "uq_remediation_active_per_finding",
        "remediation_requests",
        ["finding_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_approval', 'approved')"),
        sqlite_where=sa.text("status IN ('pending_approval', 'approved')"),
    )


def downgrade() -> None:
    op.drop_index("uq_remediation_active_per_finding", table_name="remediation_requests")
    op.drop_index("ix_remediation_status", table_name="remediation_requests")
    op.drop_index("ix_remediation_finding", table_name="remediation_requests")
    op.drop_index("ix_remediation_organization", table_name="remediation_requests")
    op.drop_table("remediation_requests")
