"""Add governed live-remediation metadata without enabling execution.

Revision ID: 0019_live_remediation_data_model
Revises: 0018_jira_integration
Create Date: 2026-08-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0019_live_remediation_data_model"
down_revision: str | None = "0018_jira_integration"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("aws_accounts", sa.Column("remediation_role_arn", sa.String(2048)))
    op.add_column("aws_accounts", sa.Column("remediation_external_id", sa.String(128)))
    op.add_column(
        "aws_accounts",
        sa.Column(
            "sandbox_approved",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "aws_accounts",
        sa.Column("sandbox_approved_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "aws_accounts",
        sa.Column("sandbox_approved_by_user_id", sa.Uuid()),
    )
    op.create_unique_constraint(
        "uq_aws_account_remediation_external_id",
        "aws_accounts",
        ["remediation_external_id"],
    )
    op.create_foreign_key(
        "fk_aws_account_sandbox_approver_membership",
        "aws_accounts",
        "organization_members",
        ["organization_id", "sandbox_approved_by_user_id"],
        ["organization_id", "user_id"],
        ondelete="RESTRICT",
    )
    bind = op.get_bind()
    existing_checks = {
        constraint["name"]
        for constraint in sa.inspect(bind).get_check_constraints("remediation_requests")
    }
    execution_mode_check = next(
        (
            name
            for name in (
                "remediation_execution_mode_allowed",
                "ck_remediation_requests_remediation_execution_mode_allowed",
            )
            if name in existing_checks
        ),
        None,
    )
    if execution_mode_check is not None:
        op.drop_constraint(
            op.f(execution_mode_check),
            "remediation_requests",
            type_="check",
        )
    op.create_check_constraint(
        "aws_account_sandbox_approval_complete",
        "aws_accounts",
        "(sandbox_approved = false AND sandbox_approved_at IS NULL "
        "AND sandbox_approved_by_user_id IS NULL) OR "
        "(sandbox_approved = true AND sandbox_approved_at IS NOT NULL "
        "AND sandbox_approved_by_user_id IS NOT NULL)",
    )

    op.add_column("remediation_requests", sa.Column("executor_key", sa.String(64)))
    op.add_column("remediation_requests", sa.Column("target_region", sa.String(64)))
    op.add_column(
        "remediation_requests", sa.Column("target_resource_arn", sa.String(2048))
    )
    op.add_column(
        "remediation_requests",
        sa.Column(
            "precondition_evidence_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "remediation_requests", sa.Column("verification_result_json", sa.JSON())
    )
    op.add_column(
        "remediation_requests", sa.Column("aws_request_ids_json", sa.JSON())
    )
    op.create_check_constraint(
        "remediation_execution_mode_allowed",
        "remediation_requests",
        "execution_mode IN ('mock_automation', 'manual', 'jira_draft', 'live_aws')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    live_rows = bind.scalar(
        sa.text(
            "SELECT count(*) FROM remediation_requests "
            "WHERE execution_mode = 'live_aws'"
        )
    )
    if live_rows:
        raise RuntimeError(
            "Cannot downgrade while live_aws remediation requests exist; "
            "migrate those rows to a previous execution mode first."
        )

    op.drop_constraint(
        "remediation_execution_mode_allowed",
        "remediation_requests",
        type_="check",
    )
    op.create_check_constraint(
        "remediation_execution_mode_allowed",
        "remediation_requests",
        "execution_mode IN ('mock_automation', 'manual', 'jira_draft')",
    )
    op.drop_column("remediation_requests", "aws_request_ids_json")
    op.drop_column("remediation_requests", "verification_result_json")
    op.drop_column("remediation_requests", "precondition_evidence_json")
    op.drop_column("remediation_requests", "target_resource_arn")
    op.drop_column("remediation_requests", "target_region")
    op.drop_column("remediation_requests", "executor_key")

    op.drop_constraint(
        "aws_account_sandbox_approval_complete", "aws_accounts", type_="check"
    )
    op.drop_constraint(
        "fk_aws_account_sandbox_approver_membership",
        "aws_accounts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_aws_account_remediation_external_id",
        "aws_accounts",
        type_="unique",
    )
    op.drop_column("aws_accounts", "sandbox_approved_by_user_id")
    op.drop_column("aws_accounts", "sandbox_approved_at")
    op.drop_column("aws_accounts", "sandbox_approved")
    op.drop_column("aws_accounts", "remediation_external_id")
    op.drop_column("aws_accounts", "remediation_role_arn")
