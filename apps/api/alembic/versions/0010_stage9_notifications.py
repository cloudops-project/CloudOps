"""Create Stage 9 notification event persistence.

Revision ID: 0010_stage9_notifications
Revises: 0009_stage7_ai_assistant
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_stage9_notifications"
down_revision: str | None = "0009_stage7_ai_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_type", sa.String(100), nullable=False),
        sa.Column("source_resource_type", sa.String(100), nullable=False),
        sa.Column("source_resource_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("destination_reference", sa.String(320)),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="pending_approval",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "channel IN ('email')",
            name="notification_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'delivered', 'failed')",
            name="notification_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="notification_event_attempt_count_nonnegative"
        ),
        sa.CheckConstraint(
            "attempt_count <= 3", name="notification_event_attempt_count_bounded"
        ),
        sa.CheckConstraint(
            "("
            "(status = 'pending_approval' AND approved_at IS NULL "
            "AND approved_by_user_id IS NULL AND delivered_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL "
            "AND delivered_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'delivered' AND approved_at IS NOT NULL "
            "AND delivered_at IS NOT NULL AND failed_at IS NULL) OR "
            "(status = 'failed' AND approved_at IS NOT NULL "
            "AND failed_at IS NOT NULL AND delivered_at IS NULL)"
            ")",
            name="notification_event_status_lifecycle",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "source_event_type",
            "source_resource_id",
            "channel",
            "template_key",
            name="uq_notification_event_dedupe_key",
        ),
    )
    op.create_index(
        "ix_notification_event_organization", "notification_events", ["organization_id"]
    )
    op.create_index("ix_notification_event_status", "notification_events", ["status"])
    op.create_index(
        "ix_notification_event_source_resource", "notification_events", ["source_resource_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_event_source_resource", table_name="notification_events"
    )
    op.drop_index("ix_notification_event_status", table_name="notification_events")
    op.drop_index("ix_notification_event_organization", table_name="notification_events")
    op.drop_table("notification_events")
