"""Create Stage 5 compliance catalog and immutable assessment snapshots.

Revision ID: 0007_stage5_compliance_engine
Revises: 0006_stage4_verification_repairs
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_stage5_compliance_engine"
down_revision: str | None = "0006_stage4_verification_repairs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "compliance_frameworks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("official_reference", sa.String(500), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("key", "version", name="uq_compliance_framework_key_version"),
    )
    op.create_table(
        "compliance_controls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("control_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("section", sa.String(200)),
        sa.Column("parent_control_id", sa.Uuid()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["framework_id"], ["compliance_frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_control_id"], ["compliance_controls.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("framework_id", "control_key", name="uq_compliance_control_key"),
        sa.UniqueConstraint("id", "framework_id", name="uq_compliance_control_id_framework"),
    )
    op.create_table(
        "rule_control_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_key", sa.String(160), nullable=False),
        sa.Column("minimum_rule_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("maximum_rule_version", sa.Integer()),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("control_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_type", sa.String(32), server_default="detective", nullable=False),
        sa.Column("rationale", sa.String(1000), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "minimum_rule_version > 0", name="rule_mapping_minimum_version_positive"
        ),
        sa.CheckConstraint(
            "maximum_rule_version IS NULL OR maximum_rule_version >= minimum_rule_version",
            name="rule_mapping_version_range_valid",
        ),
        sa.ForeignKeyConstraint(["framework_id"], ["compliance_frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["control_id", "framework_id"],
            ["compliance_controls.id", "compliance_controls.framework_id"],
            name="fk_rule_mapping_control_framework",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "rule_key",
            "minimum_rule_version",
            "maximum_rule_version",
            "control_id",
            name="uq_rule_control_version_range",
        ),
    )
    op.create_table(
        "compliance_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid()),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_job_id", sa.Uuid()),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("controls_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("controls_passed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("controls_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("controls_not_assessed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("controls_error", sa.Integer(), server_default="0", nullable=False),
        sa.Column("findings_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.String(1000)),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="compliance_assessment_status",
        ),
        sa.CheckConstraint(
            "controls_total >= 0 AND controls_passed >= 0 AND controls_failed >= 0 "
            "AND controls_not_assessed >= 0 AND controls_error >= 0 AND findings_count >= 0",
            name="assessment_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "controls_total = controls_passed + controls_failed + controls_not_assessed "
            "+ controls_error",
            name="assessment_control_counts_match",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)",
            name="assessment_status_timestamps",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_assessment_account_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"], ["compliance_frameworks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_job_id", "aws_account_id", "organization_id"],
            [
                "evaluation_jobs.id",
                "evaluation_jobs.aws_account_id",
                "evaluation_jobs.organization_id",
            ],
            name="fk_assessment_evaluation_account_organization",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "framework_id", name="uq_assessment_id_framework"),
    )
    op.create_table(
        "evaluation_rule_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("evaluation_job_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("aws_account_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", sa.String(160), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("not_applicable_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["evaluation_job_id", "aws_account_id", "organization_id"],
            [
                "evaluation_jobs.id",
                "evaluation_jobs.aws_account_id",
                "evaluation_jobs.organization_id",
            ],
            name="fk_rule_result_evaluation_account_organization",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("rule_version > 0", name="evaluation_rule_version_positive"),
        sa.CheckConstraint(
            "passed_count >= 0 AND failed_count >= 0 AND not_applicable_count >= 0 "
            "AND error_count >= 0",
            name="evaluation_rule_counts_nonnegative",
        ),
        sa.UniqueConstraint(
            "evaluation_job_id", "rule_key", "rule_version", name="uq_evaluation_rule_result"
        ),
    )
    op.create_table(
        "compliance_assessment_controls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("control_id", sa.Uuid(), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("findings_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'not_assessed', 'error')",
            name="compliance_control_status",
        ),
        sa.CheckConstraint("findings_count >= 0", name="assessment_control_findings_nonnegative"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "framework_id"],
            ["compliance_assessments.id", "compliance_assessments.framework_id"],
            name="fk_assessment_control_assessment_framework",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["control_id", "framework_id"],
            ["compliance_controls.id", "compliance_controls.framework_id"],
            name="fk_assessment_control_control_framework",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("assessment_id", "control_id", name="uq_assessment_control_snapshot"),
    )
    for name, table, columns in (
        ("ix_compliance_framework_enabled", "compliance_frameworks", ["enabled"]),
        ("ix_compliance_control_framework", "compliance_controls", ["framework_id"]),
        ("ix_rule_control_mapping_rule", "rule_control_mappings", ["rule_key"]),
        (
            "uq_rule_control_open_range",
            "rule_control_mappings",
            ["rule_key", "minimum_rule_version", "control_id"],
        ),
        ("ix_assessment_organization", "compliance_assessments", ["organization_id"]),
        ("ix_assessment_account", "compliance_assessments", ["aws_account_id"]),
        ("ix_assessment_framework", "compliance_assessments", ["framework_id"]),
        (
            "uq_active_assessment_account_framework",
            "compliance_assessments",
            ["aws_account_id", "framework_id"],
        ),
        ("ix_assessment_control_status", "compliance_assessment_controls", ["status"]),
        ("ix_evaluation_rule_result_job", "evaluation_rule_results", ["evaluation_job_id"]),
        (
            "ix_evaluation_rule_result_rule",
            "evaluation_rule_results",
            ["rule_key", "rule_version"],
        ),
    ):
        if name == "uq_rule_control_open_range":
            op.create_index(
                name,
                table,
                columns,
                unique=True,
                postgresql_where=sa.text("maximum_rule_version IS NULL"),
                sqlite_where=sa.text("maximum_rule_version IS NULL"),
            )
        elif name == "uq_active_assessment_account_framework":
            op.create_index(
                name,
                table,
                columns,
                unique=True,
                postgresql_where=sa.text("status IN ('pending', 'running')"),
                sqlite_where=sa.text("status IN ('pending', 'running')"),
            )
        else:
            op.create_index(name, table, columns)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION prevent_stage5_snapshot_update()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND NOT EXISTS (
                    SELECT 1
                    FROM compliance_assessments
                    WHERE id = OLD.assessment_id
                ) THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'compliance assessment snapshots are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_compliance_snapshot_immutable
            BEFORE UPDATE OR DELETE ON compliance_assessment_controls
            FOR EACH ROW EXECUTE FUNCTION prevent_stage5_snapshot_update()
            """
        )
        op.execute(
            """
            CREATE FUNCTION prevent_finalized_rule_result_update()
            RETURNS trigger AS $$
            DECLARE
                target_evaluation_id uuid;
            BEGIN
                target_evaluation_id := CASE
                    WHEN TG_OP = 'DELETE' THEN OLD.evaluation_job_id
                    ELSE NEW.evaluation_job_id
                END;
                IF EXISTS (
                    SELECT 1
                    FROM evaluation_jobs
                    WHERE id = target_evaluation_id
                      AND status IN ('completed', 'partially_completed', 'failed')
                ) THEN
                    RAISE EXCEPTION 'finalized evaluation rule results are immutable';
                END IF;
                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_finalized_rule_result_immutable
            BEFORE INSERT OR UPDATE OR DELETE ON evaluation_rule_results
            FOR EACH ROW EXECUTE FUNCTION prevent_finalized_rule_result_update()
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_finalized_rule_result_immutable ON evaluation_rule_results"
        )
        op.execute("DROP FUNCTION IF EXISTS prevent_finalized_rule_result_update()")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_compliance_snapshot_immutable "
            "ON compliance_assessment_controls"
        )
        op.execute("DROP FUNCTION IF EXISTS prevent_stage5_snapshot_update()")
    op.drop_table("compliance_assessment_controls")
    op.drop_table("evaluation_rule_results")
    op.drop_table("compliance_assessments")
    op.drop_table("rule_control_mappings")
    op.drop_table("compliance_controls")
    op.drop_table("compliance_frameworks")
