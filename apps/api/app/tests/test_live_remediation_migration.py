from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.tests.test_zzz_stage5_migration import POSTGRES_URL, _config, _database

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for live-remediation migration tests",
)


def _seed_0018_rows(
    engine: Any,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    metadata = sa.MetaData()
    metadata.reflect(engine)
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    account_id = uuid.uuid4()
    evaluation_id = uuid.uuid4()
    finding_id = uuid.uuid4()
    remediation_id = uuid.uuid4()
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["users"].insert(),
            {
                "id": user_id,
                "email": f"migration-{user_id}@example.invalid",
                "normalized_email": f"migration-{user_id}@example.invalid",
                "password_hash": "synthetic-migration-hash",
                "full_name": "Migration Owner",
            },
        )
        connection.execute(
            metadata.tables["organizations"].insert(),
            {
                "id": organization_id,
                "name": "Migration Tenant",
                "slug": f"migration-{organization_id}",
                "created_by_user_id": user_id,
            },
        )
        connection.execute(
            metadata.tables["organization_members"].insert(),
            {
                "id": uuid.uuid4(),
                "organization_id": organization_id,
                "user_id": user_id,
                "role": "owner",
            },
        )
        connection.execute(
            metadata.tables["aws_accounts"].insert(),
            {
                "id": account_id,
                "organization_id": organization_id,
                "name": "Existing Account",
                "account_id": "111122223333",
                "external_id": f"synthetic-{account_id}",
                "created_by_user_id": user_id,
            },
        )
        connection.execute(
            metadata.tables["evaluation_jobs"].insert(),
            {
                "id": evaluation_id,
                "organization_id": organization_id,
                "aws_account_id": account_id,
                "sequence": 1,
                "started_by_user_id": user_id,
            },
        )
        connection.execute(
            metadata.tables["findings"].insert(),
            {
                "id": finding_id,
                "organization_id": organization_id,
                "aws_account_id": account_id,
                "rule_key": "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
                "rule_version": 1,
                "severity": "high",
                "category": "storage",
                "first_seen_at": now,
                "last_seen_at": now,
                "last_evaluation_id": evaluation_id,
            },
        )
        connection.execute(
            metadata.tables["remediation_requests"].insert(),
            {
                "id": remediation_id,
                "organization_id": organization_id,
                "aws_account_id": account_id,
                "finding_id": finding_id,
                "rule_key": "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
                "rule_version": 1,
                "action_key": "legacy.manual",
                "action_version": 1,
                "idempotency_key": f"migration:{remediation_id}",
                "title": "Existing request",
                "summary": "Existing mock remediation request",
                "requested_at": now,
            },
        )
    return account_id, remediation_id, user_id, organization_id


def test_live_remediation_migration_has_one_head_and_no_provider_dependency() -> None:
    config = _config(sa.engine.make_url("postgresql://unused:unused@localhost/unused"))
    script_dir = ScriptDirectory.from_config(config)
    # 0020_invitation_delivery_state is the repository's current single head;
    # it is chained directly onto 0019 as its down_revision, so the migration
    # graph still has exactly one head and 0019 remains the direct parent.
    assert script_dir.get_heads() == ["0020_invitation_delivery_state"]
    assert (
        script_dir.get_revision("0020_invitation_delivery_state").down_revision
        == "0019_live_remediation_data_model"
    )
    migration_path = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0019_live_remediation_data_model.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    for forbidden in (
        r"\b(?:from|import)\s+boto3\b",
        r"\b(?:from|import)\s+botocore\b",
        r"\b(?:from|import)\s+httpx\b",
        r"\b(?:from|import)\s+requests\b",
        r"\b(?:from|import)\s+urllib\b",
        r"\bAWS_ACCESS_KEY\w*\b",
    ):
        assert re.search(forbidden, source) is None


@requires_postgres
def test_upgrade_from_0018_preserves_rows_and_enforces_foundation() -> None:
    with _database("live_remediation_0019") as url:
        config = _config(url)
        command.upgrade(config, "0018_jira_integration")
        engine = create_engine(url)
        account_id, remediation_id, user_id, organization_id = _seed_0018_rows(engine)

        command.upgrade(config, "0019_live_remediation_data_model")
        other_user_id = uuid.uuid4()
        other_organization_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, normalized_email, password_hash, full_name) "
                    "VALUES (:id, :email, :email, 'synthetic-hash', 'Other Owner')"
                ),
                {
                    "id": other_user_id,
                    "email": f"other-{other_user_id}@example.invalid",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_by_user_id) "
                    "VALUES (:id, 'Other Tenant', :slug, :user_id)"
                ),
                {
                    "id": other_organization_id,
                    "slug": f"other-{other_organization_id}",
                    "user_id": other_user_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO organization_members "
                    "(id, organization_id, user_id, role) "
                    "VALUES (:id, :organization_id, :user_id, 'owner')"
                ),
                {
                    "id": uuid.uuid4(),
                    "organization_id": other_organization_id,
                    "user_id": other_user_id,
                },
            )
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE aws_accounts SET sandbox_approved = true, "
                    "sandbox_approved_at = now(), "
                    "sandbox_approved_by_user_id = :other_user_id WHERE id = :account_id"
                ),
                {"account_id": account_id, "other_user_id": other_user_id},
            )
        with engine.begin() as connection:
            account = (
                connection.execute(
                    text(
                        "SELECT sandbox_approved, remediation_role_arn, "
                        "remediation_external_id FROM aws_accounts WHERE id = :id"
                    ),
                    {"id": account_id},
                )
                .mappings()
                .one()
            )
            remediation = (
                connection.execute(
                    text(
                        "SELECT execution_mode, precondition_evidence_json, executor_key "
                        "FROM remediation_requests WHERE id = :id"
                    ),
                    {"id": remediation_id},
                )
                .mappings()
                .one()
            )
            assert account == {
                "sandbox_approved": False,
                "remediation_role_arn": None,
                "remediation_external_id": None,
            }
            assert remediation["execution_mode"] == "mock_automation"
            assert remediation["precondition_evidence_json"] == {}
            assert remediation["executor_key"] is None

            connection.execute(
                text(
                    "UPDATE aws_accounts SET sandbox_approved = true, "
                    "sandbox_approved_at = now(), sandbox_approved_by_user_id = :user_id "
                    "WHERE id = :account_id"
                ),
                {"account_id": account_id, "user_id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO remediation_requests "
                    "(id, organization_id, aws_account_id, finding_id, rule_key, "
                    "rule_version, action_key, action_version, idempotency_key, title, "
                    "summary, requested_at, execution_mode, status, cancelled_at) "
                    "SELECT :live_remediation_id, organization_id, aws_account_id, "
                    "finding_id, rule_key, rule_version, action_key, action_version, "
                    ":idempotency_key, title, summary, requested_at, 'live_aws', "
                    "'cancelled', now() "
                    "FROM remediation_requests WHERE id = :remediation_id"
                ),
                {
                    "live_remediation_id": (live_remediation_id := uuid.uuid4()),
                    "idempotency_key": f"migration-live:{live_remediation_id}",
                    "remediation_id": remediation_id,
                },
            )
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM organization_members "
                    "WHERE organization_id = :organization_id AND user_id = :user_id"
                ),
                {"organization_id": organization_id, "user_id": user_id},
            )

        with pytest.raises(RuntimeError, match="live_aws remediation requests exist"):
            command.downgrade(config, "0018_jira_integration")
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM remediation_requests WHERE id = :remediation_id"),
                {"remediation_id": live_remediation_id},
            )
        command.downgrade(config, "0018_jira_integration")
        assert "remediation_role_arn" not in {
            column["name"] for column in inspect(engine).get_columns("aws_accounts")
        }
        command.upgrade(config, "head")
        command.check(config)
        engine.dispose()


@requires_postgres
def test_clean_upgrade_to_head_succeeds() -> None:
    with _database("live_remediation_clean") as url:
        config = _config(url)
        command.upgrade(config, "head")
        engine = create_engine(url)
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0020_invitation_delivery_state")
        command.check(config)
        engine.dispose()


@requires_postgres
def test_migration_failure_rolls_back_without_partial_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _database("live_remediation_rollback") as url:
        config = _config(url)
        command.upgrade(config, "0018_jira_integration")
        engine = create_engine(url)
        original = Operations.add_column
        calls = 0

        def controlled_failure(self: Operations, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("controlled_0019_failure")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Operations, "add_column", controlled_failure)
        with pytest.raises(RuntimeError, match="controlled_0019_failure"):
            command.upgrade(config, "0019_live_remediation_data_model")
        monkeypatch.setattr(Operations, "add_column", original)

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0018_jira_integration")
        assert "remediation_role_arn" not in {
            column["name"] for column in inspect(engine).get_columns("aws_accounts")
        }
        command.upgrade(config, "head")
        engine.dispose()
