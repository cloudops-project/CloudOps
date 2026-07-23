"""Create Stage 4 deterministic rule evaluation and findings.

Revision ID: 0005_stage4_rule_engine
Revises: 0004_verification_repairs
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_stage4_rule_engine"
down_revision: str | None = "0004_verification_repairs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ASSET_TYPES = (
    "ec2_instance",
    "ec2_security_group",
    "ebs_volume",
    "s3_bucket",
    "iam_user",
    "iam_role",
    "iam_group",
    "iam_policy",
    "rds_instance",
    "cloudwatch_alarm",
    "cloudwatch_log_group",
    "cloudtrail_trail",
)


def upgrade() -> None:
    op.drop_constraint("asset_type", "assets", type_="check")
    op.create_check_constraint("asset_type", "assets", f"asset_type IN {ASSET_TYPES!r}")
    op.create_unique_constraint(
        "uq_asset_id_account_organization",
        "assets",
        ["id", "aws_account_id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_discovery_job_id_account_organization",
        "discovery_jobs",
        ["id", "aws_account_id", "organization_id"],
    )

    op.create_table(
        "evaluation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("discovery_job_id", sa.Uuid()),
        sa.Column("full_evaluation", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("assets_evaluated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rules_evaluated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("passed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("not_applicable_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("findings_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("findings_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("findings_resolved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.String(2000)),
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
            "status IN ('pending','running','completed','partially_completed','failed')",
            name="evaluation_job_status",
        ),
        sa.CheckConstraint("sequence > 0", name="evaluation_sequence_positive"),
        sa.CheckConstraint("assets_evaluated >= 0", name="evaluation_assets_nonnegative"),
        sa.CheckConstraint("rules_evaluated >= 0", name="evaluation_rules_nonnegative"),
        sa.CheckConstraint("passed_count >= 0", name="evaluation_passed_nonnegative"),
        sa.CheckConstraint("failed_count >= 0", name="evaluation_failed_nonnegative"),
        sa.CheckConstraint("error_count >= 0", name="evaluation_error_nonnegative"),
        sa.CheckConstraint("not_applicable_count >= 0", name="evaluation_na_nonnegative"),
        sa.CheckConstraint("findings_created >= 0", name="evaluation_created_nonnegative"),
        sa.CheckConstraint("findings_updated >= 0", name="evaluation_updated_nonnegative"),
        sa.CheckConstraint("findings_resolved >= 0", name="evaluation_resolved_nonnegative"),
        sa.CheckConstraint(
            "("
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'partially_completed', 'failed') "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL)"
            ")",
            name="evaluation_status_timestamps",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_evaluation_job_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["discovery_job_id", "aws_account_id", "organization_id"],
            [
                "discovery_jobs.id",
                "discovery_jobs.aws_account_id",
                "discovery_jobs.organization_id",
            ],
            name="fk_evaluation_job_discovery_account_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "aws_account_id",
            "organization_id",
            name="uq_evaluation_job_id_account_organization",
        ),
    )
    op.create_index("ix_evaluation_job_organization", "evaluation_jobs", ["organization_id"])
    op.create_index("ix_evaluation_job_account", "evaluation_jobs", ["aws_account_id"])
    op.create_index("ix_evaluation_job_status", "evaluation_jobs", ["status"])
    op.create_index(
        "uq_active_evaluation_job_account",
        "evaluation_jobs",
        ["aws_account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "uq_evaluation_job_account_sequence",
        "evaluation_jobs",
        ["aws_account_id", "sequence"],
        unique=True,
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("rule_key", sa.String(160), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column("evidence_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("suppressed_at", sa.DateTime(timezone=True)),
        sa.Column("suppressed_until", sa.DateTime(timezone=True)),
        sa.Column("suppression_reason", sa.String(1000)),
        sa.Column("suppressed_by_user_id", sa.Uuid()),
        sa.Column("last_evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("lifecycle_version", sa.Integer(), server_default="0", nullable=False),
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
            "severity IN ('critical','high','medium','low','informational')",
            name="finding_severity",
        ),
        sa.CheckConstraint("status IN ('open','resolved','suppressed')", name="finding_status"),
        sa.CheckConstraint("rule_version > 0", name="finding_rule_version_positive"),
        sa.CheckConstraint("lifecycle_version >= 0", name="finding_lifecycle_version_nonnegative"),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="finding_seen_order"),
        sa.CheckConstraint(
            "("
            "(status = 'open' AND resolved_at IS NULL AND suppressed_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND suppressed_at IS NULL) OR "
            "(status = 'suppressed' AND resolved_at IS NULL AND suppressed_at IS NOT NULL "
            "AND suppression_reason IS NOT NULL AND suppression_reason <> '')"
            ")",
            name="finding_status_lifecycle",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suppressed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["last_evaluation_id"], ["evaluation_jobs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_finding_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "aws_account_id", "organization_id"],
            ["assets.id", "assets.aws_account_id", "assets.organization_id"],
            name="fk_finding_asset_account_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_finding_organization", ["organization_id"]),
        ("ix_finding_account", ["aws_account_id"]),
        ("ix_finding_asset", ["asset_id"]),
        ("ix_finding_rule", ["rule_key"]),
        ("ix_finding_status", ["status"]),
        ("ix_finding_severity", ["severity"]),
        ("ix_finding_last_seen", ["last_seen_at"]),
    ):
        op.create_index(name, "findings", columns)
    op.create_index(
        "uq_finding_asset_rule",
        "findings",
        ["asset_id", "rule_key"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "uq_finding_account_rule",
        "findings",
        ["aws_account_id", "rule_key"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("evaluation_jobs")
    op.execute(
        "DELETE FROM assets WHERE asset_type IN "
        "('ec2_security_group','ebs_volume','cloudwatch_alarm',"
        "'cloudwatch_log_group','cloudtrail_trail')"
    )
    op.drop_constraint(
        "uq_discovery_job_id_account_organization",
        "discovery_jobs",
        type_="unique",
    )
    op.drop_constraint("uq_asset_id_account_organization", "assets", type_="unique")
    op.drop_constraint("asset_type", "assets", type_="check")
    op.create_check_constraint(
        "asset_type",
        "assets",
        "asset_type IN ('ec2_instance','s3_bucket','iam_user','iam_role',"
        "'iam_group','iam_policy','rds_instance')",
    )
