"""Add demo notification delivery provider evidence.

Revision ID: 0013_demo_notification_delivery
Revises: 0012_stage11_scheduler
Create Date: 2026-07-26 03:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0013_demo_notification_delivery"
down_revision: str | None = "0012_stage11_scheduler"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("notification_events", sa.Column("provider_key", sa.String(50), nullable=True))
    op.add_column(
        "notification_events", sa.Column("provider_message_id", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("notification_events", "provider_message_id")
    op.drop_column("notification_events", "provider_key")
