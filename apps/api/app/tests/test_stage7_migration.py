from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.models import Asset, AssetRiskContext, AWSAccount, Organization, User
from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    RiskCriticality,
    RiskEnvironment,
)
from app.services.risk import RiskService
from app.tests.test_stage5_postgres import _assessment, _framework
from app.tests.test_zzz_stage5_migration import _config, _database, _seed_stage4


def _snapshot_stage1_through_stage6(engine: Any) -> dict[str, list[str]]:
    later_stage_tables = {
        "notification_events",
        "remediation_requests",
        "scan_runs",
        "scan_schedules",
    }
    with engine.connect() as connection:
        names = sorted(
            name
            for name in inspect(connection).get_table_names()
            if name != "alembic_version" and not name.startswith("ai_")
            if name not in later_stage_tables
        )
        return {
            name: list(
                connection.execute(
                    text(f'SELECT row_to_json(t)::text FROM "{name}" AS t ORDER BY 1')
                ).scalars()
            )
            for name in names
        }


def _seed_stage5_and_stage6(db: Session) -> None:
    organization = db.scalar(select(Organization).order_by(Organization.created_at))
    account = db.scalar(select(AWSAccount).order_by(AWSAccount.created_at))
    user = db.scalar(select(User).order_by(User.created_at))
    asset = db.scalar(select(Asset).order_by(Asset.created_at))
    assert organization is not None
    assert account is not None
    assert user is not None
    assert asset is not None
    framework = _framework(db, "stage7-migration")
    _assessment(db, organization, account, framework)
    db.add(
        AssetRiskContext(
            organization_id=organization.id,
            aws_account_id=account.id,
            asset_id=asset.id,
            criticality=RiskCriticality.HIGH,
            environment=RiskEnvironment.PRODUCTION,
            business_impact=BusinessImpact.HIGH,
            data_sensitivity=DataSensitivity.CONFIDENTIAL,
            source="stage7-migration-test",
            updated_by_user_id=user.id,
        )
    )
    db.commit()
    RiskService(db).assess(
        organization.id,
        user,
        aws_account_id=account.id,
        evaluation_time=datetime(2026, 7, 24, tzinfo=UTC),
    )


def test_stage7_populated_migration_preserves_stage1_through_stage6() -> None:
    with _database("stage7_populated") as url:
        config = _config(url)
        command.upgrade(config, "0006_stage4_verification_repairs")
        engine = create_engine(url)
        with Session(engine) as db, db.begin():
            _seed_stage4(db)
        command.upgrade(config, "0008_stage6_risk_scoring")
        with Session(engine) as db:
            _seed_stage5_and_stage6(db)
        before = _snapshot_stage1_through_stage6(engine)

        command.upgrade(config, "0009_stage7_ai_assistant")
        assert _snapshot_stage1_through_stage6(engine) == before
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0009_stage7_ai_assistant"
            )
            for table in ("ai_requests", "ai_request_sources", "ai_responses", "ai_usage_windows"):
                assert connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0
            assert (
                connection.execute(text("SELECT count(*) FROM ai_prompt_templates")).scalar_one()
                > 0
            )

        command.downgrade(config, "0008_stage6_risk_scoring")
        assert _snapshot_stage1_through_stage6(engine) == before
        command.upgrade(config, "0009_stage7_ai_assistant")
        assert _snapshot_stage1_through_stage6(engine) == before
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == ScriptDirectory.from_config(config).get_current_head()
            )
        command.check(config)
        engine.dispose()


def test_stage7_migration_failure_is_transactional_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _database("stage7_rollback") as url:
        config = _config(url)
        command.upgrade(config, "0006_stage4_verification_repairs")
        engine = create_engine(url)
        with Session(engine) as db, db.begin():
            _seed_stage4(db)
        command.upgrade(config, "0008_stage6_risk_scoring")
        before = _snapshot_stage1_through_stage6(engine)
        original = Operations.create_table
        calls = 0

        def controlled_failure(self: Operations, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("controlled_stage7_migration_failure")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Operations, "create_table", controlled_failure)
        with pytest.raises(RuntimeError, match="controlled_stage7_migration_failure"):
            command.upgrade(config, "0009_stage7_ai_assistant")
        monkeypatch.setattr(Operations, "create_table", original)

        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0008_stage6_risk_scoring"
            )
            tables = set(inspect(connection).get_table_names())
            assert (
                not {
                    "ai_prompt_templates",
                    "ai_requests",
                    "ai_request_sources",
                    "ai_responses",
                    "ai_usage_windows",
                }
                & tables
            )
        assert _snapshot_stage1_through_stage6(engine) == before
        command.upgrade(config, "0009_stage7_ai_assistant")
        command.upgrade(config, "head")
        command.check(config)
        engine.dispose()


def test_stage7_migration_has_no_provider_network_or_aws_dependency() -> None:
    migration_path = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0009_stage7_ai_assistant.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    for forbidden in (
        "ai_provider",
        "MockAIProvider",
        "boto3",
        "import httpx",
        "import requests",
        "from requests",
        "import urllib",
        "AWS_ACCESS_KEY",
        "provider.generate",
    ):
        assert forbidden not in source
    assert "def upgrade()" in source
