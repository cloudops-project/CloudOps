from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.models import (
    Asset,
    AuditEvent,
    AWSExternalIDReservation,
    DiscoveryJob,
    EvaluationJob,
    Finding,
    Organization,
    OrganizationMembership,
    RefreshTokenSession,
    User,
)
from app.models.enums import (
    AssetType,
    AuditResult,
    AWSAccountStatus,
    DiscoveryJobStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    InvitationStatus,
    MembershipStatus,
    OrganizationRole,
)

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 5 migration tests",
)


def _config(url: URL) -> Config:
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    return Config(str(Path(__file__).parents[2] / "alembic.ini"))


@contextmanager
def _database(label: str) -> Generator[URL, None, None]:
    assert POSTGRES_URL is not None
    source = make_url(POSTGRES_URL)
    name = f"cloudops_e2e_stage5_{label}_{uuid.uuid4().hex[:10]}"
    admin_url = source.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = source.set(database=name)
    try:
        yield url
    finally:
        engine = create_engine(url)
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _seed_stage4(db: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    owner_email = f"stage5-migration-{uuid.uuid4()}@example.com"
    other_email = f"stage5-other-{uuid.uuid4()}@example.com"
    owner = User(
        email=owner_email,
        normalized_email=owner_email,
        password_hash="migration-test-hash",
        full_name="Migration Owner",
    )
    other = User(
        email=other_email,
        normalized_email=other_email,
        password_hash="migration-test-hash",
        full_name="Migration Other",
    )
    db.add_all([owner, other])
    db.flush()
    organization = Organization(
        name="Stage 5 Migration Organization",
        slug=f"stage5-migration-{uuid.uuid4()}",
        created_by_user_id=owner.id,
    )
    second_organization = Organization(
        name="Stage 5 Migration Other",
        slug=f"stage5-other-{uuid.uuid4()}",
        created_by_user_id=other.id,
    )
    db.add_all([organization, second_organization])
    db.flush()
    db.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=other.id,
                role=OrganizationRole.AUDITOR,
                status=MembershipStatus.ACTIVE,
            ),
        ]
    )
    refresh = RefreshTokenSession(
        user_id=owner.id,
        family_id=uuid.uuid4(),
        token_hash=uuid.uuid4().hex,
        issued_at=now,
        expires_at=now,
    )
    db.add(refresh)
    db.flush()
    historical_metadata = sa.MetaData()
    # At this revision (0006_stage4_verification_repairs), the current ORM
    # invitation model's 0020 delivery columns (last_delivery_status,
    # delivery_generation, etc.) do not exist yet, so the row must be built
    # from the reflected historical table rather than the current ORM model.
    organization_invitations = sa.Table(
        "organization_invitations", historical_metadata, autoload_with=db.get_bind()
    )
    invitation_id = uuid.uuid4()
    db.execute(
        organization_invitations.insert(),
        {
            "id": invitation_id,
            "organization_id": organization.id,
            "email": "pending-migration@example.com",
            "normalized_email": "pending-migration@example.com",
            "role": OrganizationRole.VIEWER.value,
            "token_hash": uuid.uuid4().hex,
            "status": InvitationStatus.PENDING.value,
            "invited_by_user_id": owner.id,
            "expires_at": now,
        },
    )
    aws_accounts = sa.Table("aws_accounts", historical_metadata, autoload_with=db.get_bind())
    account_id = uuid.uuid4()
    external_id = f"cloudops-migration-{uuid.uuid4()}"
    db.execute(
        aws_accounts.insert(),
        {
            "id": account_id,
            "organization_id": organization.id,
            "name": "Migration account",
            "account_id": "123456789012",
            "external_id": external_id,
            "status": AWSAccountStatus.CONNECTED.value,
            "connection_status": AWSAccountStatus.CONNECTED.value,
            "created_by_user_id": owner.id,
        },
    )
    db.add(
        AWSExternalIDReservation(
            external_id=external_id,
            aws_account_id=account_id,
            organization_id=organization.id,
        )
    )
    discovery = DiscoveryJob(
        organization_id=organization.id,
        aws_account_id=account_id,
        status=DiscoveryJobStatus.COMPLETED,
        started_by_user_id=owner.id,
        started_at=now,
        finished_at=now,
    )
    db.add(discovery)
    db.flush()
    assets = [
        Asset(
            organization_id=organization.id,
            aws_account_id=account_id,
            asset_type=asset_type,
            resource_id=f"{asset_type.value}-{index}",
            name=f"Migration {asset_type.value}",
            region="us-east-1" if index == 0 else "global",
            first_seen_at=now,
            last_seen_at=now,
        )
        for index, asset_type in enumerate(
            [AssetType.EC2_INSTANCE, AssetType.S3_BUCKET, AssetType.IAM_USER]
        )
    ]
    db.add_all(assets)
    db.flush()
    evaluation = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account_id,
        discovery_job_id=discovery.id,
        sequence=1,
        status=EvaluationJobStatus.COMPLETED,
        started_by_user_id=owner.id,
        started_at=now,
        finished_at=now,
        assets_evaluated=len(assets),
        rules_evaluated=3,
        passed_count=1,
        failed_count=1,
        not_applicable_count=1,
    )
    db.add(evaluation)
    db.flush()
    findings = [
        Finding(
            organization_id=organization.id,
            aws_account_id=account_id,
            asset_id=assets[0].id,
            rule_key="EC2_SG_SSH_OPEN_TO_WORLD",
            rule_version=1,
            severity=FindingSeverity.CRITICAL,
            category="network",
            status=FindingStatus.OPEN,
            first_seen_at=now,
            last_seen_at=now,
            last_evaluation_id=evaluation.id,
        ),
        Finding(
            organization_id=organization.id,
            aws_account_id=account_id,
            asset_id=assets[1].id,
            rule_key="S3_BUCKET_LOGGING_DISABLED",
            rule_version=1,
            severity=FindingSeverity.MEDIUM,
            category="logging",
            status=FindingStatus.RESOLVED,
            first_seen_at=now,
            last_seen_at=now,
            resolved_at=now,
            last_evaluation_id=evaluation.id,
        ),
        Finding(
            organization_id=organization.id,
            aws_account_id=account_id,
            rule_key="CLOUDTRAIL_NO_ACTIVE_TRAIL",
            rule_version=1,
            severity=FindingSeverity.CRITICAL,
            category="logging",
            status=FindingStatus.SUPPRESSED,
            first_seen_at=now,
            last_seen_at=now,
            suppressed_at=now,
            suppression_reason="Migration preservation test",
            suppressed_by_user_id=owner.id,
            last_evaluation_id=evaluation.id,
        ),
    ]
    db.add_all(findings)
    db.add(
        AuditEvent(
            event_type="stage5.migration.fixture",
            resource_type="evaluation_job",
            resource_id=evaluation.id,
            organization_id=organization.id,
            actor_user_id=owner.id,
            result=AuditResult.SUCCEEDED,
        )
    )
    db.flush()
    return {
        "organization_id": organization.id,
        "account_id": account_id,
        "evaluation_id": evaluation.id,
        "evaluation_counts": (
            evaluation.rules_evaluated,
            evaluation.passed_count,
            evaluation.failed_count,
            evaluation.not_applicable_count,
        ),
        "finding_states": {finding.id: finding.status.value for finding in findings},
    }


def test_stage5_populated_migration_preserves_stage1_through_stage4_data() -> None:
    with _database("populated") as url:
        config = _config(url)
        command.upgrade(config, "0006_stage4_verification_repairs")
        engine = create_engine(url)
        with Session(engine) as db, db.begin():
            expected = _seed_stage4(db)
        before = {}
        with engine.connect() as connection:
            for table in (
                "users",
                "organizations",
                "organization_members",
                "organization_invitations",
                "refresh_token_sessions",
                "audit_events",
                "aws_accounts",
                "aws_external_id_reservations",
                "assets",
                "discovery_jobs",
                "evaluation_jobs",
                "findings",
            ):
                before[table] = connection.execute(
                    text(f'SELECT count(*) FROM "{table}"')
                ).scalar_one()

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == ScriptDirectory.from_config(config).get_current_head()
            )
            assert (
                connection.execute(
                    text(
                        "SELECT rules_evaluated, passed_count, failed_count, not_applicable_count "
                        "FROM evaluation_jobs WHERE id = :id"
                    ),
                    {"id": expected["evaluation_id"]},
                ).one()
                == expected["evaluation_counts"]
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM evaluation_rule_results WHERE evaluation_job_id = :id"
                    ),
                    {"id": expected["evaluation_id"]},
                ).scalar_one()
                == 0
            )
            states: dict[uuid.UUID, str] = {
                row.id: row.status
                for row in connection.execute(
                    text("SELECT id, status FROM findings WHERE aws_account_id = :account_id"),
                    {"account_id": expected["account_id"]},
                )
            }
            assert states == expected["finding_states"]
            for table, count in before.items():
                assert (
                    connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                    == count
                )

        command.downgrade(config, "0006_stage4_verification_repairs")
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            assert "compliance_frameworks" not in tables
            assert "evaluation_rule_results" not in tables
            assert (
                connection.execute(text("SELECT count(*) FROM findings")).scalar_one()
                == before["findings"]
            )

        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM evaluation_jobs WHERE id = :id"),
                    {"id": expected["evaluation_id"]},
                ).scalar_one()
                == 1
            )
        engine.dispose()


def test_stage5_migration_failure_rolls_back_transactional_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _database("rollback") as url:
        config = _config(url)
        command.upgrade(config, "0006_stage4_verification_repairs")
        engine = create_engine(url)
        with Session(engine) as db, db.begin():
            expected = _seed_stage4(db)

        original = Operations.create_table
        calls = 0

        def fail_third_table(self: Operations, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("controlled_stage5_migration_failure")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Operations, "create_table", fail_third_table)
        with pytest.raises(RuntimeError, match="controlled_stage5_migration_failure"):
            command.upgrade(config, "head")
        monkeypatch.setattr(Operations, "create_table", original)

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0006_stage4_verification_repairs")
            tables = set(inspect(connection).get_table_names())
            assert "compliance_frameworks" not in tables
            assert "compliance_controls" not in tables
            assert "rule_control_mappings" not in tables
            assert (
                connection.execute(
                    text("SELECT count(*) FROM evaluation_jobs WHERE id = :id"),
                    {"id": expected["evaluation_id"]},
                ).scalar_one()
                == 1
            )
        command.upgrade(config, "head")
        engine.dispose()
