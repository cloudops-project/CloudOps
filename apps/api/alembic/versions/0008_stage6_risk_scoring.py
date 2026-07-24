"""Create Stage 6 deterministic risk scoring and immutable snapshots.

Revision ID: 0008_stage6_risk_scoring
Revises: 0007_stage5_compliance_engine
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_stage6_risk_scoring"
down_revision: str | None = "0007_stage5_compliance_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_finding_id_account_organization",
        "findings",
        ["id", "aws_account_id", "organization_id"],
    )
    op.create_table(
        "risk_scoring_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("weights_json", sa.JSON(), nullable=False),
        sa.Column("bands_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="risk_policy_version_positive"),
        sa.UniqueConstraint("key", "version", name="uq_risk_policy_key_version"),
    )
    op.create_table(
        "asset_risk_contexts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("criticality", sa.String(32), server_default="unknown", nullable=False),
        sa.Column("environment", sa.String(32), server_default="unknown", nullable=False),
        sa.Column("business_impact", sa.String(32), server_default="unknown", nullable=False),
        sa.Column("data_sensitivity", sa.String(32), server_default="unknown", nullable=False),
        sa.Column("source", sa.String(64), server_default="manual", nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "criticality IN ('critical', 'high', 'medium', 'low', 'unknown')",
            name="risk_criticality",
        ),
        sa.CheckConstraint(
            "environment IN ('production', 'staging', 'development', 'sandbox', 'unknown')",
            name="risk_environment",
        ),
        sa.CheckConstraint(
            "business_impact IN ('critical', 'high', 'medium', 'low', 'unknown')",
            name="business_impact",
        ),
        sa.CheckConstraint(
            "data_sensitivity IN ('restricted', 'confidential', 'internal', 'public', 'unknown')",
            name="data_sensitivity",
        ),
        sa.CheckConstraint("version > 0", name="risk_context_version_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_risk_context_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "aws_account_id", "organization_id"],
            ["assets.id", "assets.aws_account_id", "assets.organization_id"],
            name="fk_risk_context_asset_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid()),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("findings_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("critical_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("high_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("medium_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("low_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("informational_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accounts_scored", sa.Integer(), server_default="0", nullable=False),
        sa.Column("aggregate_score", sa.Integer()),
        sa.Column("aggregate_priority", sa.String(32)),
        sa.Column("error_code", sa.String(100)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="risk_assessment_status",
        ),
        sa.CheckConstraint(
            "aggregate_priority IS NULL OR aggregate_priority IN "
            "('critical', 'high', 'medium', 'low')",
            name="risk_priority",
        ),
        sa.CheckConstraint(
            "findings_total >= 0 AND critical_count >= 0 AND high_count >= 0 "
            "AND medium_count >= 0 AND low_count >= 0 AND informational_count >= 0 "
            "AND accounts_scored >= 0",
            name="risk_assessment_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "findings_total = critical_count + high_count + medium_count + low_count "
            "+ informational_count",
            name="risk_assessment_counts_match",
        ),
        sa.CheckConstraint(
            "aggregate_score IS NULL OR (aggregate_score >= 0 AND aggregate_score <= 100)",
            name="risk_assessment_score_range",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)",
            name="risk_assessment_status_timestamps",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_risk_assessment_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["policy_id"], ["risk_scoring_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "organization_id", name="uq_risk_assessment_id_organization"),
    )
    op.create_table(
        "compensating_controls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("score_adjustment", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "score_adjustment BETWEEN -15 AND -1",
            name="compensating_control_adjustment_range",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="compensating_control_expiry_order",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_compensating_control_finding_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "finding_risk_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("source_finding_version", sa.Integer(), nullable=False),
        sa.Column("source_finding_status", sa.String(32), nullable=False),
        sa.Column("policy_key", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("severity_points", sa.Integer(), nullable=False),
        sa.Column("exposure_points", sa.Integer(), nullable=False),
        sa.Column("exploitability_points", sa.Integer(), nullable=False),
        sa.Column("privilege_points", sa.Integer(), nullable=False),
        sa.Column("asset_criticality_points", sa.Integer(), nullable=False),
        sa.Column("environment_points", sa.Integer(), nullable=False),
        sa.Column("business_impact_points", sa.Integer(), nullable=False),
        sa.Column("data_sensitivity_points", sa.Integer(), nullable=False),
        sa.Column("age_points", sa.Integer(), nullable=False),
        sa.Column("compensating_adjustment", sa.Integer(), server_default="0", nullable=False),
        sa.Column("component_codes_json", sa.JSON(), nullable=False),
        sa.Column("unknown_inputs_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_finding_status IN ('open', 'resolved', 'suppressed')",
            name="risk_source_finding_status",
        ),
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="finding_risk_priority",
        ),
        sa.CheckConstraint("policy_version > 0", name="finding_risk_policy_version_positive"),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100", name="finding_risk_score_range"
        ),
        sa.CheckConstraint(
            "severity_points BETWEEN 0 AND 30 AND exposure_points BETWEEN 0 AND 15 "
            "AND exploitability_points BETWEEN 0 AND 10 AND privilege_points BETWEEN 0 AND 10 "
            "AND asset_criticality_points BETWEEN 0 AND 10 "
            "AND environment_points BETWEEN 0 AND 5 "
            "AND business_impact_points BETWEEN 0 AND 10 "
            "AND data_sensitivity_points BETWEEN 0 AND 5 "
            "AND age_points BETWEEN 0 AND 5",
            name="finding_risk_component_ranges",
        ),
        sa.CheckConstraint(
            "compensating_adjustment BETWEEN -15 AND 0",
            name="finding_risk_adjustment_range",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_finding_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_finding_risk_finding_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("assessment_id", "finding_id", name="uq_finding_risk_snapshot"),
    )
    op.create_table(
        "account_risk_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("highest_finding_score", sa.Integer(), nullable=False),
        sa.Column("top_ten_mean", sa.Integer(), nullable=False),
        sa.Column("all_findings_mean", sa.Integer(), nullable=False),
        sa.Column("findings_total", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="account_risk_priority",
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100 AND highest_finding_score BETWEEN 0 AND 100 "
            "AND top_ten_mean BETWEEN 0 AND 100 AND all_findings_mean BETWEEN 0 AND 100 "
            "AND findings_total >= 0",
            name="account_risk_ranges",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_account_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_account_risk_account_organization",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("assessment_id", "aws_account_id", name="uq_account_risk_snapshot"),
    )
    op.create_table(
        "organization_risk_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("highest_account_score", sa.Integer(), nullable=False),
        sa.Column("mean_account_score", sa.Integer(), nullable=False),
        sa.Column("accounts_total", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="organization_risk_priority",
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100 AND highest_account_score BETWEEN 0 AND 100 "
            "AND mean_account_score BETWEEN 0 AND 100 AND accounts_total >= 0",
            name="organization_risk_ranges",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_organization_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("assessment_id", name="uq_organization_risk_snapshot"),
    )
    _indexes()
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_guards()


def _indexes() -> None:
    for name, table, columns in (
        ("ix_risk_policy_active", "risk_scoring_policies", ["active"]),
        ("ix_risk_context_organization", "asset_risk_contexts", ["organization_id"]),
        ("ix_risk_context_account", "asset_risk_contexts", ["aws_account_id"]),
        ("ix_risk_assessment_organization", "risk_assessments", ["organization_id"]),
        ("ix_risk_assessment_account", "risk_assessments", ["aws_account_id"]),
        ("ix_risk_assessment_status", "risk_assessments", ["status"]),
        ("ix_compensating_control_organization", "compensating_controls", ["organization_id"]),
        ("ix_compensating_control_finding", "compensating_controls", ["finding_id"]),
        ("ix_finding_risk_organization", "finding_risk_snapshots", ["organization_id"]),
        ("ix_finding_risk_account", "finding_risk_snapshots", ["aws_account_id"]),
        ("ix_finding_risk_finding", "finding_risk_snapshots", ["finding_id"]),
        ("ix_finding_risk_score", "finding_risk_snapshots", ["risk_score"]),
        ("ix_finding_risk_priority", "finding_risk_snapshots", ["priority"]),
        ("ix_account_risk_organization", "account_risk_snapshots", ["organization_id"]),
        ("ix_account_risk_account", "account_risk_snapshots", ["aws_account_id"]),
        ("ix_account_risk_score", "account_risk_snapshots", ["risk_score"]),
        (
            "ix_organization_risk_organization",
            "organization_risk_snapshots",
            ["organization_id"],
        ),
    ):
        op.create_index(name, table, columns)
    op.create_index(
        "uq_risk_context_asset",
        "asset_risk_contexts",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
        sqlite_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "uq_risk_context_account_default",
        "asset_risk_contexts",
        ["aws_account_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NULL"),
        sqlite_where=sa.text("asset_id IS NULL"),
    )
    op.create_index(
        "uq_active_risk_assessment_account",
        "risk_assessments",
        ["organization_id", "aws_account_id", "policy_id"],
        unique=True,
        postgresql_where=sa.text("aws_account_id IS NOT NULL AND status IN ('pending', 'running')"),
        sqlite_where=sa.text("aws_account_id IS NOT NULL AND status IN ('pending', 'running')"),
    )
    op.create_index(
        "uq_active_risk_assessment_organization",
        "risk_assessments",
        ["organization_id", "policy_id"],
        unique=True,
        postgresql_where=sa.text("aws_account_id IS NULL AND status IN ('pending', 'running')"),
        sqlite_where=sa.text("aws_account_id IS NULL AND status IN ('pending', 'running')"),
    )
    op.create_index(
        "uq_active_compensating_control_finding",
        "compensating_controls",
        ["finding_id"],
        unique=True,
        postgresql_where=sa.text("active"),
        sqlite_where=sa.text("active = 1"),
    )


def _postgresql_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_stage6_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Stage 6 risk snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "finding_risk_snapshots",
        "account_risk_snapshots",
        "organization_risk_snapshots",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION prevent_stage6_snapshot_mutation()
            """
        )
    op.execute(
        """
        CREATE FUNCTION prevent_used_risk_policy_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM risk_assessments WHERE policy_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'used risk scoring policies are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_used_risk_policy_immutable
        BEFORE UPDATE OR DELETE ON risk_scoring_policies
        FOR EACH ROW EXECUTE FUNCTION prevent_used_risk_policy_mutation()
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_used_risk_policy_immutable ON risk_scoring_policies")
        op.execute("DROP FUNCTION IF EXISTS prevent_used_risk_policy_mutation()")
        for table in (
            "finding_risk_snapshots",
            "account_risk_snapshots",
            "organization_risk_snapshots",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS prevent_stage6_snapshot_mutation()")
    op.drop_table("organization_risk_snapshots")
    op.drop_table("account_risk_snapshots")
    op.drop_table("finding_risk_snapshots")
    op.drop_table("compensating_controls")
    op.drop_table("risk_assessments")
    op.drop_table("asset_risk_contexts")
    op.drop_table("risk_scoring_policies")
    op.drop_constraint("uq_finding_id_account_organization", "findings", type_="unique")
