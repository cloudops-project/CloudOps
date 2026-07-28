"""Add tenant-scoped notification delivery evidence.

Revision ID: 0015_notification_evidence
Revises: 0014_distributed_platform_jobs
Create Date: 2026-07-27 04:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0015_notification_evidence"
down_revision: str | None = "0014_distributed_platform_jobs"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_events",
        sa.Column("approved_delivery_fingerprint", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_notification_event_id_organization",
        "notification_events",
        ["id", "organization_id"],
    )
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("notification_event_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("destination_reference", sa.String(100), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("response_classification", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_summary", sa.String(500), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 20",
            name="ck_notification_delivery_attempts_notification_delivery_attempt_number",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_notification_delivery_attempts_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notification_event_id", "organization_id"],
            ["notification_events.id", "notification_events.organization_id"],
            name="fk_notification_delivery_event_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_delivery_attempts"),
        sa.UniqueConstraint(
            "notification_event_id",
            "attempt_number",
            name="uq_notification_delivery_event_attempt",
        ),
    )
    op.create_index(
        "ix_notification_delivery_organization_attempted",
        "notification_delivery_attempts",
        ["organization_id", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_delivery_organization_attempted",
        table_name="notification_delivery_attempts",
    )
    op.drop_table("notification_delivery_attempts")
    op.drop_constraint(
        "uq_notification_event_id_organization",
        "notification_events",
        type_="unique",
    )
    op.drop_column("notification_events", "approved_delivery_fingerprint")
