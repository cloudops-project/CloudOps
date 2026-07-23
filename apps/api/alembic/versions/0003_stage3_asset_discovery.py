"""Create Stage 3 asset inventory and discovery jobs.

Revision ID: 0003_stage3
Revises: 0002_stage2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_stage3"
down_revision: str | None = "0002_stage2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(512), nullable=False),
        sa.Column("arn", sa.String(2048)),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("status", sa.String(128)),
        sa.Column("tags", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "asset_type IN ('ec2_instance','s3_bucket','iam_user','iam_role','iam_group','iam_policy','rds_instance')",
            name="asset_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aws_account_id"], ["aws_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "aws_account_id", "asset_type", "resource_id", name="uq_asset_identity"
        ),
    )
    for name, column in (
        ("ix_asset_organization", "organization_id"),
        ("ix_asset_aws_account", "aws_account_id"),
        ("ix_asset_type", "asset_type"),
        ("ix_asset_region", "region"),
        ("ix_asset_status", "status"),
        ("ix_asset_is_active", "is_active"),
        ("ix_asset_last_seen", "last_seen_at"),
    ):
        op.create_index(name, "assets", [column])
    op.create_table(
        "discovery_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("assets_discovered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assets_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assets_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assets_deactivated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.String(2000)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partially_completed','failed')",
            name="discovery_job_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aws_account_id"], ["aws_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_job_organization", "discovery_jobs", ["organization_id"])
    op.create_index("ix_discovery_job_account", "discovery_jobs", ["aws_account_id"])
    op.create_index("ix_discovery_job_status", "discovery_jobs", ["status"])
    op.create_index(
        "uq_active_discovery_job_account",
        "discovery_jobs",
        ["aws_account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("discovery_jobs")
    op.drop_table("assets")
