"""Create Stage 2 cross-account AWS onboarding records.

Revision ID: 0002_stage2
Revises: 0001_stage1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stage2"
down_revision: str | None = "0001_stage1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aws_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("account_id", sa.String(12), nullable=False),
        sa.Column("role_arn", sa.String(2048)),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("connection_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("failure_reason", sa.String(100)),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'failed', 'disconnected')",
            name="aws_account_status",
        ),
        sa.CheckConstraint(
            "connection_status IN ('pending', 'connected', 'failed', 'disconnected')",
            name="aws_connection_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "account_id", name="uq_aws_account_org_account"),
        sa.UniqueConstraint("organization_id", "role_arn", name="uq_aws_account_org_role_arn"),
        sa.UniqueConstraint("external_id", name="uq_aws_account_external_id"),
    )
    op.create_index("ix_aws_account_organization", "aws_accounts", ["organization_id"])
    op.create_index("ix_aws_account_status", "aws_accounts", ["status"])
    op.create_index("ix_aws_account_connection_status", "aws_accounts", ["connection_status"])


def downgrade() -> None:
    op.drop_table("aws_accounts")
