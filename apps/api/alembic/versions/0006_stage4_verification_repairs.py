"""Repair Stage 4 verification gaps.

Revision ID: 0006_stage4_verification_repairs
Revises: 0005_stage4_rule_engine
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_stage4_verification_repairs"
down_revision: str | None = "0005_stage4_rule_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_jobs",
        sa.Column("findings_reopened", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "evaluation_jobs",
        sa.Column("evaluation_errors", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "evaluation_reopened_nonnegative",
        "evaluation_jobs",
        "findings_reopened >= 0",
    )
    op.create_check_constraint(
        "evaluation_errors_nonnegative",
        "evaluation_jobs",
        "evaluation_errors >= 0",
    )
    op.drop_constraint("finding_status_lifecycle", "findings", type_="check")
    op.create_check_constraint(
        "finding_status_lifecycle",
        "findings",
        "("
        "(status = 'open' AND resolved_at IS NULL AND suppressed_at IS NULL "
        "AND suppressed_by_user_id IS NULL) OR "
        "(status = 'resolved' AND resolved_at IS NOT NULL AND suppressed_at IS NULL "
        "AND suppressed_by_user_id IS NULL) OR "
        "(status = 'suppressed' AND resolved_at IS NULL AND suppressed_at IS NOT NULL "
        "AND suppression_reason IS NOT NULL AND suppression_reason <> '' "
        "AND suppressed_by_user_id IS NOT NULL)"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("finding_status_lifecycle", "findings", type_="check")
    op.create_check_constraint(
        "finding_status_lifecycle",
        "findings",
        "("
        "(status = 'open' AND resolved_at IS NULL AND suppressed_at IS NULL) OR "
        "(status = 'resolved' AND resolved_at IS NOT NULL AND suppressed_at IS NULL) OR "
        "(status = 'suppressed' AND resolved_at IS NULL AND suppressed_at IS NOT NULL "
        "AND suppression_reason IS NOT NULL AND suppression_reason <> '')"
        ")",
    )
    op.drop_constraint(
        "evaluation_errors_nonnegative",
        "evaluation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "evaluation_reopened_nonnegative",
        "evaluation_jobs",
        type_="check",
    )
    op.drop_column("evaluation_jobs", "evaluation_errors")
    op.drop_column("evaluation_jobs", "findings_reopened")
