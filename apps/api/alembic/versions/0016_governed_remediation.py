"""Add immutable governed-remediation request controls.

Revision ID: 0016_governed_remediation
Revises: 0015_notification_evidence
Create Date: 2026-07-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0016_governed_remediation"
down_revision: str | None = "0015_notification_evidence"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "remediation_requests",
        sa.Column(
            "action_key",
            sa.String(160),
            server_default="legacy.manual",
            nullable=False,
        ),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("action_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "remediation_requests",
        sa.Column(
            "preview_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "remediation_requests",
        sa.Column(
            "request_snapshot_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "remediation_requests",
        sa.Column(
            "request_snapshot_hash",
            sa.String(64),
            server_default="0" * 64,
            nullable=False,
        ),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("approved_snapshot_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("execution_lease_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "remediation_requests",
        sa.Column("dry_run", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.execute(
        "UPDATE remediation_requests "
        "SET idempotency_key = 'legacy:' || CAST(id AS VARCHAR)"
    )
    op.alter_column("remediation_requests", "idempotency_key", nullable=False)
    op.create_index(
        "uq_remediation_tenant_idempotency",
        "remediation_requests",
        ["organization_id", "idempotency_key"],
        unique=True,
    )
    op.execute(
        """
        CREATE FUNCTION cloudops_prevent_remediation_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.organization_id IS DISTINCT FROM NEW.organization_id
               OR OLD.aws_account_id IS DISTINCT FROM NEW.aws_account_id
               OR OLD.finding_id IS DISTINCT FROM NEW.finding_id
               OR OLD.rule_key IS DISTINCT FROM NEW.rule_key
               OR OLD.rule_version IS DISTINCT FROM NEW.rule_version
               OR OLD.action_key IS DISTINCT FROM NEW.action_key
               OR OLD.action_version IS DISTINCT FROM NEW.action_version
               OR OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key
               OR OLD.preview_json IS DISTINCT FROM NEW.preview_json
               OR OLD.request_snapshot_json IS DISTINCT FROM NEW.request_snapshot_json
               OR OLD.request_snapshot_hash IS DISTINCT FROM NEW.request_snapshot_hash
               OR OLD.execution_mode IS DISTINCT FROM NEW.execution_mode
               OR OLD.dry_run IS DISTINCT FROM NEW.dry_run
            THEN
                RAISE EXCEPTION 'remediation request snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_remediation_request_snapshot_immutable
        BEFORE UPDATE ON remediation_requests
        FOR EACH ROW EXECUTE FUNCTION cloudops_prevent_remediation_snapshot_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_remediation_request_snapshot_immutable "
        "ON remediation_requests"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS cloudops_prevent_remediation_snapshot_mutation()"
    )
    op.drop_index(
        "uq_remediation_tenant_idempotency",
        table_name="remediation_requests",
    )
    op.drop_column("remediation_requests", "dry_run")
    op.drop_column("remediation_requests", "execution_lease_id")
    op.drop_column("remediation_requests", "approved_snapshot_hash")
    op.drop_column("remediation_requests", "request_snapshot_hash")
    op.drop_column("remediation_requests", "request_snapshot_json")
    op.drop_column("remediation_requests", "preview_json")
    op.drop_column("remediation_requests", "idempotency_key")
    op.drop_column("remediation_requests", "action_version")
    op.drop_column("remediation_requests", "action_key")
