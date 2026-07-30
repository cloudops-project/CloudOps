"""Create organization-scoped Jira Cloud integration and issue-link tables.

Revision ID: 0018_jira_integration
Revises: 0017_remediation_json_trigger
Create Date: 2026-07-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0018_jira_integration"
down_revision: str | None = "0017_remediation_json_trigger"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "jira_integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("default_issue_type", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("api_token_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'failed', 'disconnected')",
            name="jira_integration_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_jira_integration_id_organization"
        ),
    )
    op.create_index(
        "ix_jira_integration_organization", "jira_integrations", ["organization_id"]
    )
    op.create_index(
        "uq_jira_integration_active_per_organization",
        "jira_integrations",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("status != 'disconnected'"),
        sqlite_where=sa.text("status != 'disconnected'"),
    )

    op.create_table(
        "jira_issue_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("jira_integration_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid()),
        sa.Column("remediation_request_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("issue_url", sa.String(500), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["remediation_request_id"], ["remediation_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["jira_integration_id", "organization_id"],
            ["jira_integrations.id", "jira_integrations.organization_id"],
            name="fk_jira_issue_link_integration_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_jira_issue_link_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_jira_issue_link_organization", "jira_issue_links", ["organization_id"]
    )
    op.create_index("ix_jira_issue_link_finding", "jira_issue_links", ["finding_id"])
    op.create_index(
        "ix_jira_issue_link_remediation_request",
        "jira_issue_links",
        ["remediation_request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_jira_issue_link_remediation_request", table_name="jira_issue_links")
    op.drop_index("ix_jira_issue_link_finding", table_name="jira_issue_links")
    op.drop_index("ix_jira_issue_link_organization", table_name="jira_issue_links")
    op.drop_table("jira_issue_links")
    op.drop_index(
        "uq_jira_integration_active_per_organization", table_name="jira_integrations"
    )
    op.drop_index("ix_jira_integration_organization", table_name="jira_integrations")
    op.drop_table("jira_integrations")
