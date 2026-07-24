from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AssetRiskContext,
    FindingRiskSnapshot,
    RiskAssessment,
    RiskScoringPolicy,
)
from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    RiskAssessmentStatus,
    RiskCriticality,
    RiskEnvironment,
)
from app.services.risk import RiskService
from app.tests.test_risk import _finding, _tenant

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test" or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError("Stage 6 PostgreSQL tests require a disposable CloudOps test database.")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 6 integrity tests",
)


@pytest.fixture(scope="module")
def pg_sessions() -> Generator[sessionmaker[Session], None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _policy(db: Session) -> RiskScoringPolicy:
    return RiskService(db).ensure_policy()


def test_risk_database_ranges_and_tenant_constraints(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user_a, org_a, account_a = _tenant(db)
        user_b, org_b, account_b = _tenant(db)
        finding_a, asset_a = _finding(db, org_a, account_a, user_a)
        db.commit()

        db.add(
            AssetRiskContext(
                organization_id=org_b.id,
                aws_account_id=account_b.id,
                asset_id=asset_a.id,
                criticality=RiskCriticality.HIGH,
                environment=RiskEnvironment.PRODUCTION,
                business_impact=BusinessImpact.HIGH,
                data_sensitivity=DataSensitivity.CONFIDENTIAL,
                source="manual",
                updated_by_user_id=user_b.id,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assessment = RiskService(db).assess(
            org_a.id,
            user_a,
            aws_account_id=account_a.id,
            evaluation_time=datetime(2026, 7, 24, tzinfo=UTC),
        )
        snapshot = db.scalar(
            select(FindingRiskSnapshot).where(
                FindingRiskSnapshot.assessment_id == assessment.id,
                FindingRiskSnapshot.finding_id == finding_a.id,
            )
        )
        assert snapshot is not None
        with pytest.raises(DatabaseError, match="immutable"):
            db.execute(
                text(
                    "UPDATE finding_risk_snapshots SET risk_score = 101 "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": str(snapshot.id)},
            )
        db.rollback()


def test_completed_risk_snapshots_are_immutable(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        _finding(db, organization, account, user)
        db.commit()
        assessment = RiskService(db).assess(
            organization.id,
            user,
            aws_account_id=account.id,
            evaluation_time=datetime(2026, 7, 24, tzinfo=UTC),
        )
        snapshot = db.scalar(
            select(FindingRiskSnapshot).where(FindingRiskSnapshot.assessment_id == assessment.id)
        )
        assert snapshot is not None
        with pytest.raises(DatabaseError, match="immutable"):
            db.execute(
                text(
                    "UPDATE finding_risk_snapshots SET risk_score = risk_score - 1 "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": str(snapshot.id)},
            )
        db.rollback()
        with pytest.raises(DatabaseError, match="immutable"):
            db.execute(
                text("DELETE FROM finding_risk_snapshots WHERE id = CAST(:id AS uuid)"),
                {"id": str(snapshot.id)},
            )
        db.rollback()


def test_active_assessment_unique_under_independent_sessions(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as setup:
        user, organization, account = _tenant(setup)
        policy = _policy(setup)
        setup.commit()
        values = {
            "organization_id": organization.id,
            "account_id": account.id,
            "policy_id": policy.id,
            "user_id": user.id,
        }

    barrier = Barrier(2)

    def insert_pending() -> str:
        with pg_sessions() as db:
            assessment = RiskAssessment(
                organization_id=values["organization_id"],
                aws_account_id=values["account_id"],
                policy_id=values["policy_id"],
                evaluation_time=datetime(2026, 7, 24, tzinfo=UTC),
                source_cutoff_at=datetime(2026, 7, 24, tzinfo=UTC),
                status=RiskAssessmentStatus.PENDING,
                started_by_user_id=values["user_id"],
            )
            db.add(assessment)
            barrier.wait(timeout=10)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: insert_pending(), range(2)))
    assert sorted(results) == ["conflict", "created"]


def test_context_optimistic_lock_rejects_stale_worker(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as setup:
        user, organization, account = _tenant(setup)
        setup.commit()
        values = (user.id, organization.id, account.id)
    barrier = Barrier(2)

    def update(criticality: RiskCriticality) -> str:
        with pg_sessions() as db:
            try:
                barrier.wait(timeout=10)
                db.execute(
                    text(
                        "INSERT INTO asset_risk_contexts "
                        "(id, organization_id, aws_account_id, asset_id, criticality, "
                        "environment, business_impact, data_sensitivity, source, "
                        "updated_by_user_id, version, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :organization_id, :account_id, NULL, "
                        ":criticality, 'unknown', 'unknown', 'unknown', 'manual', "
                        ":user_id, 1, now(), now())"
                    ),
                    {
                        "organization_id": values[1],
                        "account_id": values[2],
                        "criticality": criticality.value,
                        "user_id": values[0],
                    },
                )
                db.commit()
            except IntegrityError:
                db.rollback()
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                update,
                (RiskCriticality.HIGH, RiskCriticality.CRITICAL),
            )
        )
    assert sorted(results) == ["conflict", "created"]
