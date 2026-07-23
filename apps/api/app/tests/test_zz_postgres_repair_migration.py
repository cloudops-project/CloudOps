from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from alembic import command
from app.core.config import get_settings

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for PostgreSQL migration tests",
)


def test_repair_migration_backfills_and_preserves_stage2_and_stage3_data() -> None:
    assert POSTGRES_TEST_DATABASE_URL is not None
    database_name = make_url(POSTGRES_TEST_DATABASE_URL).database or ""
    assert database_name == "cloudops_test" or database_name.startswith("cloudops_e2e_")
    os.environ["DATABASE_URL"] = POSTGRES_TEST_DATABASE_URL
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(POSTGRES_TEST_DATABASE_URL)

    command.downgrade(config, "0003_stage3")

    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    account_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    job_id = uuid.uuid4()
    external_id = f"migration-external-{uuid.uuid4()}"
    email = f"migration-{uuid.uuid4()}@example.com"

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (
                    id, email, normalized_email, password_hash, full_name
                ) VALUES (
                    :id, :email, :email, 'migration-test-hash', 'Migration Test'
                )
                """
            ),
            {"id": user_id, "email": email},
        )
        connection.execute(
            text(
                """
                INSERT INTO organizations (id, name, slug, created_by_user_id)
                VALUES (:id, 'Migration Organization', :slug, :user_id)
                """
            ),
            {
                "id": organization_id,
                "slug": f"migration-{uuid.uuid4()}",
                "user_id": user_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO aws_accounts (
                    id, organization_id, name, account_id, external_id,
                    status, connection_status, created_by_user_id
                ) VALUES (
                    :id, :organization_id, 'Migration Account', '123456789012',
                    :external_id, 'connected', 'connected', :user_id
                )
                """
            ),
            {
                "id": account_id,
                "organization_id": organization_id,
                "external_id": external_id,
                "user_id": user_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO assets (
                    id, organization_id, aws_account_id, asset_type, resource_id,
                    name, region, first_seen_at, last_seen_at
                ) VALUES (
                    :id, :organization_id, :account_id, 'ec2_instance',
                    'i-migration', 'Migration Asset', 'us-east-1', now(), now()
                )
                """
            ),
            {
                "id": asset_id,
                "organization_id": organization_id,
                "account_id": account_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO discovery_jobs (
                    id, organization_id, aws_account_id, status, started_by_user_id
                ) VALUES (
                    :id, :organization_id, :account_id, 'pending', :user_id
                )
                """
            ),
            {
                "id": job_id,
                "organization_id": organization_id,
                "account_id": account_id,
                "user_id": user_id,
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        account = connection.execute(
            text("SELECT external_id FROM aws_accounts WHERE id = :id"), {"id": account_id}
        ).scalar_one()
        reservation = connection.execute(
            text(
                """
                SELECT external_id, aws_account_id, organization_id
                FROM aws_external_id_reservations
                WHERE external_id = :external_id
                """
            ),
            {"external_id": external_id},
        ).one()
        assert account == external_id
        assert reservation == (external_id, account_id, organization_id)
        assert (
            connection.execute(
                text("SELECT count(*) FROM assets WHERE id = :id"), {"id": asset_id}
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM discovery_jobs WHERE id = :id"), {"id": job_id}
            ).scalar_one()
            == 1
        )

    command.downgrade(config, "0003_stage3")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT external_id FROM aws_accounts WHERE id = :id"), {"id": account_id}
            ).scalar_one()
            == external_id
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM assets WHERE id = :id"), {"id": asset_id}
            ).scalar_one()
            == 1
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    """
                SELECT count(*) FROM aws_external_id_reservations
                WHERE external_id = :external_id
                """
                ),
                {"external_id": external_id},
            ).scalar_one()
            == 1
        )

    engine.dispose()
