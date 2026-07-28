"""Make remediation snapshot trigger comparisons valid for PostgreSQL JSON.

Revision ID: 0017_remediation_json_trigger
Revises: 0016_governed_remediation
Create Date: 2026-07-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision: str = "0017_remediation_json_trigger"
down_revision: str | None = "0016_governed_remediation"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cloudops_prevent_remediation_snapshot_mutation()
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
               OR OLD.preview_json::jsonb IS DISTINCT FROM NEW.preview_json::jsonb
               OR OLD.request_snapshot_json::jsonb
                  IS DISTINCT FROM NEW.request_snapshot_json::jsonb
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


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cloudops_prevent_remediation_snapshot_mutation()
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
