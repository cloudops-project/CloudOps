"""Repair Stage 2 lifecycle security and Stage 3 tenant integrity.

Revision ID: 0004_verification_repairs
Revises: 0003_stage3
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_verification_repairs"
down_revision: str | None = "0003_stage3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_existing_data_is_valid() -> None:
    connection = op.get_bind()
    checks = {
        "cross-tenant assets": sa.text(
            "SELECT count(*) FROM assets a JOIN aws_accounts aa ON aa.id = a.aws_account_id "
            "WHERE a.organization_id <> aa.organization_id"
        ),
        "cross-tenant discovery jobs": sa.text(
            "SELECT count(*) FROM discovery_jobs j "
            "JOIN aws_accounts aa ON aa.id = j.aws_account_id "
            "WHERE j.organization_id <> aa.organization_id"
        ),
        "invalid asset seen timestamps": sa.text(
            "SELECT count(*) FROM assets WHERE last_seen_at < first_seen_at"
        ),
        "negative discovery counters": sa.text(
            "SELECT count(*) FROM discovery_jobs WHERE assets_discovered < 0 "
            "OR assets_created < 0 OR assets_updated < 0 OR assets_deactivated < 0"
        ),
        "invalid discovery status timestamps": sa.text(
            "SELECT count(*) FROM discovery_jobs WHERE NOT ("
            "(status = 'pending' AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND (error_summary IS NULL OR error_summary = '')) OR "
            "(status = 'partially_completed' AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL) OR "
            "(status = 'failed' AND started_at IS NOT NULL AND finished_at IS NOT NULL)"
            ")"
        ),
    }
    failures = [name for name, statement in checks.items() if connection.scalar(statement)]
    if failures:
        raise RuntimeError(
            "Stage 2/3 repair migration refused invalid existing data: " + ", ".join(failures)
        )


def upgrade() -> None:
    _assert_existing_data_is_valid()

    op.add_column("aws_accounts", sa.Column("validation_token", sa.Uuid()))
    op.add_column("aws_accounts", sa.Column("validation_started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "aws_accounts",
        sa.Column("lifecycle_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint(
        "uq_aws_account_id_organization", "aws_accounts", ["id", "organization_id"]
    )

    reservations = op.create_table(
        "aws_external_id_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("aws_account_id", sa.Uuid()),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["aws_account_id"], ["aws_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_aws_external_id_reservation_external_id"),
        sa.UniqueConstraint("aws_account_id", name="uq_aws_external_id_reservation_account"),
    )
    connection = op.get_bind()
    existing = connection.execute(
        sa.text(
            "SELECT id, organization_id, external_id, created_at FROM aws_accounts "
            "ORDER BY created_at, id"
        )
    ).mappings()
    op.bulk_insert(
        reservations,
        [
            {
                "id": uuid.uuid4(),
                "external_id": row["external_id"],
                "aws_account_id": row["id"],
                "organization_id": row["organization_id"],
                "issued_at": row["created_at"],
                "created_at": row["created_at"],
            }
            for row in existing
        ],
    )

    op.drop_constraint("fk_assets_aws_account_id_aws_accounts", "assets", type_="foreignkey")
    op.create_foreign_key(
        "fk_asset_account_organization",
        "assets",
        "aws_accounts",
        ["aws_account_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_assets_asset_seen_order", "assets", "last_seen_at >= first_seen_at"
    )

    op.drop_constraint(
        "fk_discovery_jobs_aws_account_id_aws_accounts",
        "discovery_jobs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_discovery_job_account_organization",
        "discovery_jobs",
        "aws_accounts",
        ["aws_account_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="CASCADE",
    )
    for name, column in (
        ("ck_discovery_jobs_discovery_assets_discovered_nonnegative", "assets_discovered"),
        ("ck_discovery_jobs_discovery_assets_created_nonnegative", "assets_created"),
        ("ck_discovery_jobs_discovery_assets_updated_nonnegative", "assets_updated"),
        ("ck_discovery_jobs_discovery_assets_deactivated_nonnegative", "assets_deactivated"),
    ):
        op.create_check_constraint(name, "discovery_jobs", f"{column} >= 0")
    op.create_check_constraint(
        "ck_discovery_jobs_discovery_status_timestamps",
        "discovery_jobs",
        "("
        "(status = 'pending' AND finished_at IS NULL) OR "
        "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
        "(status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
        "AND (error_summary IS NULL OR error_summary = '')) OR "
        "(status = 'partially_completed' AND started_at IS NOT NULL "
        "AND finished_at IS NOT NULL) OR "
        "(status = 'failed' AND started_at IS NOT NULL AND finished_at IS NOT NULL)"
        ")",
    )

    if connection.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION prevent_aws_external_id_reservation_delete()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'AWS external ID reservations are immutable';
            END;
            $$
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_prevent_aws_external_id_reservation_delete
            BEFORE DELETE ON aws_external_id_reservations
            FOR EACH ROW EXECUTE FUNCTION prevent_aws_external_id_reservation_delete()
            """
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_prevent_aws_external_id_reservation_delete "
            "ON aws_external_id_reservations"
        )
        op.execute("DROP FUNCTION IF EXISTS prevent_aws_external_id_reservation_delete()")

    op.drop_constraint(
        "ck_discovery_jobs_discovery_status_timestamps",
        "discovery_jobs",
        type_="check",
    )
    for name in (
        "ck_discovery_jobs_discovery_assets_deactivated_nonnegative",
        "ck_discovery_jobs_discovery_assets_updated_nonnegative",
        "ck_discovery_jobs_discovery_assets_created_nonnegative",
        "ck_discovery_jobs_discovery_assets_discovered_nonnegative",
    ):
        op.drop_constraint(name, "discovery_jobs", type_="check")
    op.drop_constraint(
        "fk_discovery_job_account_organization", "discovery_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_discovery_jobs_aws_account_id_aws_accounts",
        "discovery_jobs",
        "aws_accounts",
        ["aws_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("ck_assets_asset_seen_order", "assets", type_="check")
    op.drop_constraint("fk_asset_account_organization", "assets", type_="foreignkey")
    op.create_foreign_key(
        "fk_assets_aws_account_id_aws_accounts",
        "assets",
        "aws_accounts",
        ["aws_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_table("aws_external_id_reservations")
    op.drop_constraint("uq_aws_account_id_organization", "aws_accounts", type_="unique")
    op.drop_column("aws_accounts", "lifecycle_version")
    op.drop_column("aws_accounts", "validation_started_at")
    op.drop_column("aws_accounts", "validation_token")
