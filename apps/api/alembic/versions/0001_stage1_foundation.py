"""Create Stage 1 identity, tenant, session, invitation, and audit tables.

Revision ID: 0001_stage1
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_stage1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[object]]:
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
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'invited', 'suspended', 'disabled')",
            name="user_status",
        ),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )
    op.create_index("ix_users_normalized_email", "users", ["normalized_email"])

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'disabled')",
            name="organization_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid()),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'security_analyst', 'cloud_engineer', 'auditor', 'viewer')",
            name="organization_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'removed')",
            name="membership_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index(
        "ix_membership_org_status", "organization_members", ["organization_id", "status"]
    )
    op.create_index("ix_membership_user_status", "organization_members", ["user_id", "status"])

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'security_analyst', 'cloud_engineer', 'auditor', 'viewer')",
            name="invitation_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'cancelled', 'expired')",
            name="invitation_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index("ix_invitation_token_hash", "organization_invitations", ["token_hash"])
    op.create_index(
        "ix_invitation_org_status",
        "organization_invitations",
        ["organization_id", "status"],
    )
    op.create_index(
        "uq_active_invitation_org_email",
        "organization_invitations",
        ["organization_id", "normalized_email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "refresh_token_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", sa.Uuid()),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("ip_address", sa.String(45)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_token_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )
    op.create_index("ix_refresh_token_hash", "refresh_token_sessions", ["token_hash"])
    op.create_index("ix_refresh_user_family", "refresh_token_sessions", ["user_id", "family_id"])
    op.create_index("ix_refresh_expires_at", "refresh_token_sessions", ["expires_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid()),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "result IN ('succeeded', 'failed', 'denied')",
            name="audit_result",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_org_created", "audit_events", ["organization_id", "created_at"])
    op.create_index("ix_audit_actor_created", "audit_events", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("refresh_token_sessions")
    op.drop_table("organization_invitations")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("users")
