from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError, DataError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db_session
from app.exceptions.errors import ConflictError
from app.main import app
from app.models import (
    Asset,
    AuditEvent,
    AWSAccount,
    ComplianceAssessment,
    ComplianceAssessmentControl,
    ComplianceControl,
    ComplianceFramework,
    EvaluationJob,
    EvaluationRuleResult,
    Finding,
    Organization,
    OrganizationMembership,
    RuleControlMapping,
    User,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    ComplianceAssessmentStatus,
    ComplianceControlStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    MembershipStatus,
    OrganizationRole,
)
from app.security.tokens import create_access_token
from app.services import evaluations as evaluations_module
from app.services.compliance import ComplianceService
from app.services.evaluations import EvaluationService
from app.tests.conftest import register_and_login

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test" or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError("Stage 5 PostgreSQL tests require a disposable CloudOps test database.")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 5 integrity tests",
)


@pytest.fixture(scope="module")
def pg_sessions() -> Generator[sessionmaker[Session], None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def pg_client(pg_sessions: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override() -> Generator[Session, None, None]:
        with pg_sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = override
    client = TestClient(app, base_url="http://testserver")
    yield client
    client.close()
    app.dependency_overrides.clear()


def _framework(db: Session, suffix: str) -> ComplianceFramework:
    bounded_suffix = suffix[:20]
    framework = ComplianceFramework(
        key=f"stage5-{bounded_suffix}-{uuid.uuid4().hex[:12]}",
        name=f"Stage 5 {suffix}",
        version="1.0",
        description="CloudOps-authored test summary.",
        official_reference="https://example.invalid/framework",
    )
    db.add(framework)
    db.flush()
    return framework


def _control(db: Session, framework: ComplianceFramework, key: str = "C-1") -> ComplianceControl:
    control = ComplianceControl(
        framework_id=framework.id,
        control_key=key,
        title="Test control",
        description="CloudOps-authored test control.",
    )
    db.add(control)
    db.flush()
    return control


def _tenant_account(db: Session, suffix: str) -> tuple[User, Organization, AWSAccount]:
    marker = uuid.uuid4().hex
    user = User(
        email=f"stage5-{suffix}-{marker}@example.com",
        normalized_email=f"stage5-{suffix}-{marker}@example.com",
        password_hash="test-only-password-hash",
        full_name="Stage 5 Test",
    )
    db.add(user)
    db.flush()
    organization = Organization(
        name=f"Stage 5 {suffix}",
        slug=f"stage5-{suffix}-{marker}",
        created_by_user_id=user.id,
    )
    db.add(organization)
    db.flush()
    account_id = str(uuid.uuid4().int % 1_000_000_000_000).zfill(12)
    account = AWSAccount(
        organization_id=organization.id,
        name="Stage 5 account",
        account_id=account_id,
        external_id=f"cloudops-stage5-{marker}",
        created_by_user_id=user.id,
    )
    db.add(account)
    db.flush()
    return user, organization, account


def _active_member(
    db: Session,
    user: User,
    organization: Organization,
    role: OrganizationRole = OrganizationRole.OWNER,
) -> None:
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.flush()


def _evaluable_account(db: Session, suffix: str) -> tuple[User, Organization, AWSAccount, Asset]:
    user, organization, account = _tenant_account(db, suffix)
    _active_member(db, user, organization)
    account.status = AWSAccountStatus.CONNECTED
    account.connection_status = AWSAccountStatus.CONNECTED
    now = datetime.now(UTC)
    asset = Asset(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id=f"sg-{uuid.uuid4().hex[:12]}",
        name="Stage 5 atomicity security group",
        region="us-east-1",
        metadata_json={
            "ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ]
        },
        tags={},
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(asset)
    db.flush()
    return user, organization, account, asset


def _assessment(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    framework: ComplianceFramework,
    *,
    status: ComplianceAssessmentStatus = ComplianceAssessmentStatus.COMPLETED,
) -> ComplianceAssessment:
    now = datetime.now(UTC)
    assessment = ComplianceAssessment(
        organization_id=organization.id,
        aws_account_id=account.id,
        framework_id=framework.id,
        status=status,
        started_at=now if status != ComplianceAssessmentStatus.PENDING else None,
        finished_at=now
        if status in {ComplianceAssessmentStatus.COMPLETED, ComplianceAssessmentStatus.FAILED}
        else None,
    )
    db.add(assessment)
    db.flush()
    return assessment


def _evaluation(
    db: Session,
    user: User,
    organization: Organization,
    account: AWSAccount,
    *,
    status: EvaluationJobStatus = EvaluationJobStatus.COMPLETED,
    sequence: int = 1,
    rules_evaluated: int = 0,
    passed_count: int = 0,
    error_count: int = 0,
) -> EvaluationJob:
    now = datetime.now(UTC)
    job = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account.id,
        sequence=sequence,
        started_by_user_id=user.id,
        status=status,
        started_at=now,
        finished_at=now if status == EvaluationJobStatus.COMPLETED else None,
        rules_evaluated=rules_evaluated,
        passed_count=passed_count,
        error_count=error_count,
        evaluation_errors=error_count,
    )
    db.add(job)
    db.flush()
    return job


def test_postgres_stage5_framework_control_and_mapping_constraints(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        framework = _framework(db, "catalog")
        control = _control(db, framework)
        duplicate = ComplianceFramework(
            key=framework.key,
            name="Duplicate",
            version=framework.version,
            description="Duplicate",
            official_reference="https://example.invalid/duplicate",
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        first_framework = _framework(db, "same-control-key-a")
        second_framework = _framework(db, "same-control-key-b")
        _control(db, first_framework, "SHARED-1")
        _control(db, second_framework, "SHARED-1")

    with pg_sessions.begin() as db:
        framework = _framework(db, "mapping")
        control = _control(db, framework)
        db.add(
            RuleControlMapping(
                rule_key="STAGE5_TEST_RULE",
                minimum_rule_version=2,
                maximum_rule_version=1,
                framework_id=framework.id,
                control_id=control.id,
                rationale="Invalid range",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        framework = _framework(db, "duplicate-control")
        _control(db, framework)
        db.add(
            ComplianceControl(
                framework_id=framework.id,
                control_key="C-1",
                title="Duplicate",
                description="Duplicate",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_cross_tenant_assessment_is_rejected(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        _user_a, _org_a, account_a = _tenant_account(db, "tenant-a")
        _user_b, org_b, _account_b = _tenant_account(db, "tenant-b")
        framework = _framework(db, "tenant")
        db.add(
            ComplianceAssessment(
                organization_id=org_b.id,
                aws_account_id=account_a.id,
                framework_id=framework.id,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_mapping_and_evaluation_tenant_consistency(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        framework = _framework(db, "mapping-framework-a")
        other_framework = _framework(db, "mapping-framework-b")
        control = _control(db, framework)
        db.add(
            RuleControlMapping(
                rule_key="STAGE5_WRONG_FRAMEWORK",
                minimum_rule_version=1,
                framework_id=other_framework.id,
                control_id=control.id,
                rationale="Must be rejected by the composite foreign key.",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        user_a, organization_a, account_a = _tenant_account(db, "evaluation-tenant-a")
        _user_b, organization_b, account_b = _tenant_account(db, "evaluation-tenant-b")
        evaluation = _evaluation(db, user_a, organization_a, account_a)
        framework = _framework(db, "evaluation-tenant")
        db.add(
            ComplianceAssessment(
                organization_id=organization_b.id,
                aws_account_id=account_b.id,
                framework_id=framework.id,
                evaluation_job_id=evaluation.id,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_rule_result_identity_counts_and_tenant_constraints(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "rule-result")
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        result = EvaluationRuleResult(
            evaluation_job_id=evaluation.id,
            organization_id=organization.id,
            aws_account_id=account.id,
            rule_key="STAGE5_RESULT_RULE",
            rule_version=1,
            passed_count=1,
        )
        db.add(result)
        db.flush()
        evaluation.status = EvaluationJobStatus.COMPLETED
        evaluation.finished_at = datetime.now(UTC)
        db.flush()
        result_id = result.id

    with pg_sessions.begin() as db:
        loaded_result = db.get(EvaluationRuleResult, result_id)
        assert loaded_result is not None
        loaded_result.passed_count = 2
        with pytest.raises(DatabaseError):
            db.flush()

    with pg_sessions.begin() as db:
        loaded_result = db.get(EvaluationRuleResult, result_id)
        assert loaded_result is not None
        db.delete(loaded_result)
        with pytest.raises(DatabaseError):
            db.flush()

    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "rule-result-negative")
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        db.add(
            EvaluationRuleResult(
                evaluation_job_id=evaluation.id,
                organization_id=organization.id,
                aws_account_id=account.id,
                rule_key="STAGE5_NEGATIVE_RESULT",
                rule_version=1,
                error_count=-1,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        user_a, organization_a, account_a = _tenant_account(db, "summary-tenant-a")
        _user_b, organization_b, account_b = _tenant_account(db, "summary-tenant-b")
        evaluation = _evaluation(
            db, user_a, organization_a, account_a, status=EvaluationJobStatus.RUNNING
        )
        db.add(
            EvaluationRuleResult(
                evaluation_job_id=evaluation.id,
                organization_id=organization_b.id,
                aws_account_id=account_b.id,
                rule_key="STAGE5_CROSS_TENANT_RESULT",
                rule_version=1,
                passed_count=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_snapshot_update_is_rejected(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, "immutable-snapshot")
        framework = _framework(db, "immutable-snapshot")
        control = _control(db, framework)
        assessment = _assessment(db, organization, account, framework)
        snapshot = ComplianceAssessmentControl(
            assessment_id=assessment.id,
            control_id=control.id,
            framework_id=framework.id,
            status=ComplianceControlStatus.PASS,
            assessed_at=datetime.now(UTC),
        )
        db.add(snapshot)
        db.flush()
        snapshot_id = snapshot.id

    with pg_sessions.begin() as db:
        loaded_snapshot = db.get(ComplianceAssessmentControl, snapshot_id)
        assert loaded_snapshot is not None
        loaded_snapshot.status = ComplianceControlStatus.FAIL
        with pytest.raises(DatabaseError):
            db.flush()

    with pg_sessions.begin() as db:
        loaded_snapshot = db.get(ComplianceAssessmentControl, snapshot_id)
        assert loaded_snapshot is not None
        db.delete(loaded_snapshot)
        with pytest.raises(DatabaseError):
            db.flush()


@pytest.mark.parametrize(
    "status,started_at,finished_at",
    [
        (ComplianceAssessmentStatus.PENDING, datetime.now(UTC), None),
        (ComplianceAssessmentStatus.RUNNING, datetime.now(UTC), datetime.now(UTC)),
        (ComplianceAssessmentStatus.COMPLETED, datetime.now(UTC), None),
        (ComplianceAssessmentStatus.FAILED, None, datetime.now(UTC)),
    ],
)
def test_postgres_stage5_invalid_assessment_lifecycle_is_rejected(
    pg_sessions: sessionmaker[Session],
    status: ComplianceAssessmentStatus,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, f"lifecycle-{status.value}")
        framework = _framework(db, f"lifecycle-{status.value}")
        db.add(
            ComplianceAssessment(
                organization_id=organization.id,
                aws_account_id=account.id,
                framework_id=framework.id,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_rule_result_duplicate_and_bounds_are_rejected(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "summary-duplicate")
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        values = {
            "evaluation_job_id": evaluation.id,
            "organization_id": organization.id,
            "aws_account_id": account.id,
            "rule_key": "STAGE5_DUPLICATE_SUMMARY",
            "rule_version": 1,
            "passed_count": 1,
        }
        db.add_all([EvaluationRuleResult(**values), EvaluationRuleResult(**values)])
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "summary-oversized")
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        db.add(
            EvaluationRuleResult(
                evaluation_job_id=evaluation.id,
                organization_id=organization.id,
                aws_account_id=account.id,
                rule_key="R" * 161,
                rule_version=1,
                passed_count=1,
            )
        )
        with pytest.raises(DataError):
            db.flush()


@pytest.mark.parametrize("maximum_rule_version", [5, None])
def test_postgres_stage5_concurrent_mapping_range_is_unique(
    pg_sessions: sessionmaker[Session], maximum_rule_version: int | None
) -> None:
    with pg_sessions.begin() as db:
        framework = _framework(db, f"bounded-race-{maximum_rule_version}")
        control = _control(db, framework)
        framework_id, control_id = framework.id, control.id
    barrier = Barrier(2)

    def insert_mapping() -> bool:
        with pg_sessions() as db:
            db.add(
                RuleControlMapping(
                    rule_key=f"STAGE5_RANGE_{maximum_rule_version}",
                    minimum_rule_version=2,
                    maximum_rule_version=maximum_rule_version,
                    framework_id=framework_id,
                    control_id=control_id,
                    rationale="Concurrent version-range test.",
                )
            )
            barrier.wait(timeout=10)
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: insert_mapping(), range(2)))
    assert sorted(outcomes) == [False, True]


def test_postgres_stage5_concurrent_rule_summary_is_unique(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "summary-race")
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        ids = evaluation.id, organization.id, account.id
    evaluation_id, organization_id, account_id = ids
    barrier = Barrier(2)

    def insert_summary() -> bool:
        with pg_sessions() as db:
            db.add(
                EvaluationRuleResult(
                    evaluation_job_id=evaluation_id,
                    organization_id=organization_id,
                    aws_account_id=account_id,
                    rule_key="STAGE5_SUMMARY_RACE",
                    rule_version=1,
                    passed_count=1,
                )
            )
            barrier.wait(timeout=10)
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: insert_summary(), range(2)))
    assert sorted(outcomes) == [False, True]


def test_postgres_stage5_snapshot_framework_and_identity_constraints(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, "snapshot")
        framework = _framework(db, "snapshot-a")
        other_framework = _framework(db, "snapshot-b")
        control = _control(db, framework)
        other_control = _control(db, other_framework)
        assessment = _assessment(db, organization, account, framework)
        db.add(
            ComplianceAssessmentControl(
                assessment_id=assessment.id,
                control_id=other_control.id,
                framework_id=framework.id,
                status=ComplianceControlStatus.PASS,
                assessed_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()

    with pg_sessions.begin() as db:
        framework = _framework(db, "snapshot-duplicate")
        control = _control(db, framework)
        _user, organization, account = _tenant_account(db, "snapshot-duplicate")
        assessment = _assessment(db, organization, account, framework)
        first = ComplianceAssessmentControl(
            assessment_id=assessment.id,
            control_id=control.id,
            framework_id=framework.id,
            status=ComplianceControlStatus.PASS,
            assessed_at=datetime.now(UTC),
        )
        db.add(first)
        db.flush()
        db.add(
            ComplianceAssessmentControl(
                assessment_id=assessment.id,
                control_id=control.id,
                framework_id=framework.id,
                status=ComplianceControlStatus.FAIL,
                assessed_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


@pytest.mark.parametrize(
    "field,value",
    [
        ("controls_total", -1),
        ("controls_passed", -1),
        ("controls_failed", -1),
        ("controls_not_assessed", -1),
        ("controls_error", -1),
    ],
)
def test_postgres_stage5_negative_assessment_counters_are_rejected(
    pg_sessions: sessionmaker[Session], field: str, value: int
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, f"negative-{field}")
        framework = _framework(db, f"negative-{field}")
        assessment = _assessment(db, organization, account, framework)
        setattr(assessment, field, value)
        with pytest.raises(IntegrityError):
            db.flush()


def test_postgres_stage5_historical_snapshots_remain_distinct(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, "history")
        framework = _framework(db, "history")
        control = _control(db, framework)
        assessments = [
            _assessment(db, organization, account, framework),
            _assessment(db, organization, account, framework),
        ]
        for index, assessment in enumerate(assessments):
            db.add(
                ComplianceAssessmentControl(
                    assessment_id=assessment.id,
                    control_id=control.id,
                    framework_id=framework.id,
                    status=(
                        ComplianceControlStatus.PASS if index == 0 else ComplianceControlStatus.FAIL
                    ),
                    assessed_at=datetime.now(UTC),
                )
            )
    with pg_sessions() as db:
        rows = db.scalars(
            select(ComplianceAssessmentControl).where(
                ComplianceAssessmentControl.assessment_id.in_(
                    [assessment.id for assessment in assessments]
                )
            )
        ).all()
        assert len(rows) == 2


def test_postgres_stage5_concurrent_active_assessment_is_unique(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        _user, organization, account = _tenant_account(db, "assessment-race")
        framework = _framework(db, "assessment-race")
        ids = organization.id, account.id, framework.id
    organization_id, account_id, framework_id = ids
    barrier = Barrier(2)

    def insert_active() -> bool:
        with pg_sessions() as db:
            db.add(
                ComplianceAssessment(
                    organization_id=organization_id,
                    aws_account_id=account_id,
                    framework_id=framework_id,
                    status=ComplianceAssessmentStatus.RUNNING,
                    started_at=datetime.now(UTC),
                )
            )
            barrier.wait(timeout=10)
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: insert_active(), range(2)))
    assert sorted(outcomes) == [False, True]
    with pg_sessions() as db:
        active = db.scalars(
            select(ComplianceAssessment).where(
                ComplianceAssessment.aws_account_id == account_id,
                ComplianceAssessment.framework_id == framework_id,
                ComplianceAssessment.status == ComplianceAssessmentStatus.RUNNING,
            )
        ).all()
        assert len(active) == 1


def test_postgres_stage5_concurrent_mapping_insert_is_unique(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        framework = _framework(db, "mapping-race")
        control = _control(db, framework)
        ids = framework.id, control.id
    framework_id, control_id = ids
    barrier = Barrier(2)

    def insert_mapping() -> bool:
        with pg_sessions() as db:
            db.add(
                RuleControlMapping(
                    rule_key="STAGE5_CONCURRENT_RULE",
                    minimum_rule_version=1,
                    framework_id=framework_id,
                    control_id=control_id,
                    rationale="Concurrent deterministic mapping test.",
                )
            )
            barrier.wait(timeout=10)
            try:
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: insert_mapping(), range(2)))
    assert sorted(outcomes) == [False, True]


def test_postgres_stage5_service_rejects_overlapping_assessment_start(
    pg_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "service-assessment-race")
        _active_member(db, user, organization)
        ComplianceService(db).ensure_catalog()
        ids = user.id, account.id
    user_id, account_id = ids
    entered = Event()
    release = Event()
    original = ComplianceService._source_evaluation

    def hold_source(
        self: ComplianceService,
        locked_account_id: uuid.UUID,
        organization_id: uuid.UUID,
        evaluation_job_id: uuid.UUID | None,
    ) -> tuple[EvaluationJob | None, ComplianceControlStatus]:
        entered.set()
        assert release.wait(timeout=10)
        return original(
            self,
            locked_account_id,
            organization_id,
            evaluation_job_id,
        )

    monkeypatch.setattr(ComplianceService, "_source_evaluation", hold_source)

    def assess() -> ComplianceAssessment:
        with pg_sessions() as db:
            actor = db.get(User, user_id)
            assert actor is not None
            return ComplianceService(db).assess(account_id, actor, "cis_aws", None, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(assess)
        assert entered.wait(timeout=10)
        second = pool.submit(assess)
        second_result: ComplianceAssessment | Exception
        try:
            second_result = second.result(timeout=10)
        except Exception as exc:
            second_result = exc
        release.set()
        first_result = first.result(timeout=10)

    assert isinstance(first_result, ComplianceAssessment)
    assert isinstance(second_result, ConflictError)
    with pg_sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "compliance.assessment.started",
                    AuditEvent.resource_id == first_result.id,
                )
            )
            == 1
        )


def test_postgres_stage5_different_accounts_and_organizations_do_not_share_locks(
    pg_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pg_sessions.begin() as db:
        first_user, first_org, first_account = _tenant_account(db, "parallel-first")
        second_user, second_org, second_account = _tenant_account(db, "parallel-second")
        _active_member(db, first_user, first_org)
        _active_member(db, second_user, second_org)
        ComplianceService(db).ensure_catalog()
        ids = [
            (first_user.id, first_account.id),
            (second_user.id, second_account.id),
        ]
    barrier = Barrier(2)
    original = ComplianceService._source_evaluation

    def synchronized_source(
        self: ComplianceService,
        account_id: uuid.UUID,
        organization_id: uuid.UUID,
        evaluation_job_id: uuid.UUID | None,
    ) -> tuple[EvaluationJob | None, ComplianceControlStatus]:
        barrier.wait(timeout=10)
        return original(self, account_id, organization_id, evaluation_job_id)

    monkeypatch.setattr(ComplianceService, "_source_evaluation", synchronized_source)

    def assess(pair: tuple[uuid.UUID, uuid.UUID]) -> ComplianceAssessment:
        user_id, account_id = pair
        with pg_sessions() as db:
            actor = db.get(User, user_id)
            assert actor is not None
            return ComplianceService(db).assess(account_id, actor, "cis_aws", None, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(assess, ids))
    assert len(outcomes) == 2
    assert outcomes[0].organization_id != outcomes[1].organization_id


def test_postgres_stage5_assessment_never_reads_uncommitted_rule_summaries(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions.begin() as db:
        user, organization, account = _tenant_account(db, "finalization-visibility")
        _active_member(db, user, organization)
        evaluation = _evaluation(
            db, user, organization, account, status=EvaluationJobStatus.RUNNING
        )
        ComplianceService(db).ensure_catalog()
        ids = user.id, organization.id, account.id, evaluation.id
    user_id, organization_id, account_id, evaluation_id = ids
    inserted = Event()
    release = Event()

    def finalize() -> None:
        with pg_sessions() as db:
            evaluation = db.get(EvaluationJob, evaluation_id)
            assert evaluation is not None
            summary = EvaluationRuleResult(
                evaluation_job_id=evaluation.id,
                organization_id=organization_id,
                aws_account_id=account_id,
                rule_key="EC2_SG_SSH_OPEN_TO_WORLD",
                rule_version=1,
                passed_count=1,
            )
            db.add(summary)
            db.flush()
            inserted.set()
            assert release.wait(timeout=10)
            evaluation.status = EvaluationJobStatus.COMPLETED
            evaluation.finished_at = datetime.now(UTC)
            evaluation.rules_evaluated = 1
            evaluation.passed_count = 1
            db.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(finalize)
        assert inserted.wait(timeout=10)
        with pg_sessions() as db:
            actor = db.get(User, user_id)
            assert actor is not None
            assessment = ComplianceService(db).assess(
                account_id, actor, "cis_aws", None, evaluation_id
            )
            assert assessment.controls_passed == 0
            assert assessment.controls_not_assessed > 0
        release.set()
        worker.result(timeout=10)


def test_postgres_stage5_public_http_rbac_filters_and_tenant_isolation(
    pg_client: TestClient,
    pg_sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = uuid.uuid4().hex
    owner_email = f"stage5-http-owner-{marker}@example.com"
    owner_headers = register_and_login(pg_client, owner_email)
    organization_response = pg_client.post(
        "/api/v1/organizations",
        headers=owner_headers,
        json={"name": "Stage 5 HTTP", "slug": f"stage5-http-{marker}"},
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]
    account_response = pg_client.post(
        "/api/v1/aws/accounts",
        headers=owner_headers,
        json={
            "organization_id": organization_id,
            "name": "Stage 5 API account",
            "account_id": str(uuid.uuid4().int % 1_000_000_000_000).zfill(12),
        },
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["account"]["id"]
    frameworks_response = pg_client.get(
        "/api/v1/compliance/frameworks",
        headers=owner_headers,
        params={"organization_id": organization_id},
    )
    assert frameworks_response.status_code == 200
    framework = frameworks_response.json()[0]
    controls_response = pg_client.get(
        f"/api/v1/compliance/frameworks/{framework['key']}/controls",
        headers=owner_headers,
        params={"organization_id": organization_id},
    )
    assert controls_response.status_code == 200
    control = controls_response.json()[0]
    assert (
        pg_client.get(
            f"/api/v1/compliance/controls/{control['id']}/rules",
            headers=owner_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 200
    )
    finding_links = pg_client.get(
        f"/api/v1/compliance/controls/{control['id']}/findings",
        headers=owner_headers,
        params={
            "organization_id": organization_id,
            "aws_account_id": account_id,
            "severity": "critical",
            "service": "ec2",
            "region": "us-east-1",
            "rule_key": "EC2_SG_SSH_OPEN_TO_WORLD",
            "search": "SSH",
            "page": 1,
            "page_size": 10,
        },
    )
    assert finding_links.status_code == 200
    assert finding_links.json()["total"] == 0
    assert finding_links.json()["finding_ids"] == []
    assert (
        pg_client.get(
            f"/api/v1/compliance/controls/{control['id']}/findings",
            headers=owner_headers,
            params={"organization_id": organization_id, "page_size": 101},
        ).status_code
        == 422
    )

    role_headers: dict[OrganizationRole, dict[str, str]] = {OrganizationRole.OWNER: owner_headers}
    for role in (
        OrganizationRole.ADMIN,
        OrganizationRole.SECURITY_ANALYST,
        OrganizationRole.CLOUD_ENGINEER,
        OrganizationRole.AUDITOR,
        OrganizationRole.VIEWER,
    ):
        email = f"stage5-http-{role.value}-{marker}@example.com"
        headers = register_and_login(pg_client, email)
        with pg_sessions.begin() as db:
            user = db.scalar(select(User).where(User.normalized_email == email))
            assert user is not None
            db.add(
                OrganizationMembership(
                    organization_id=uuid.UUID(organization_id),
                    user_id=user.id,
                    role=role,
                    status=MembershipStatus.ACTIVE,
                )
            )
        role_headers[role] = headers

    assessment_ids: list[str] = []
    for role, headers in role_headers.items():
        assert (
            pg_client.get(
                "/api/v1/compliance/frameworks",
                headers=headers,
                params={"organization_id": organization_id},
            ).status_code
            == 200
        )
        response = pg_client.post(
            f"/api/v1/aws/accounts/{account_id}/compliance/assess",
            headers=headers,
            json={
                "framework_key": framework["key"],
                "framework_version": framework["version"],
            },
        )
        if role in {
            OrganizationRole.OWNER,
            OrganizationRole.ADMIN,
            OrganizationRole.SECURITY_ANALYST,
            OrganizationRole.CLOUD_ENGINEER,
        }:
            assert response.status_code == 201, response.text
            assessment_ids.append(response.json()["id"])
        else:
            assert response.status_code == 403

    assessment_id = assessment_ids[0]
    detail = pg_client.get(
        f"/api/v1/compliance/assessments/{assessment_id}",
        headers=role_headers[OrganizationRole.VIEWER],
        params={"organization_id": organization_id},
    )
    assert detail.status_code == 200
    assert detail.json()["controls"]
    snapshot_id = detail.json()["controls"][0]["id"]
    assert (
        pg_client.get(
            f"/api/v1/compliance/assessments/{assessment_id}/controls/{snapshot_id}",
            headers=role_headers[OrganizationRole.AUDITOR],
            params={"organization_id": organization_id},
        ).status_code
        == 200
    )
    filtered = pg_client.get(
        "/api/v1/compliance/assessments",
        headers=owner_headers,
        params={
            "organization_id": organization_id,
            "framework_key": framework["key"],
            "framework_version": framework["version"],
            "aws_account_id": account_id,
            "assessment_status": "completed",
            "control_status": "not_assessed",
            "search": "CIS",
            "page": 1,
            "page_size": 2,
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 4
    assert len(filtered.json()["items"]) == 2
    assert (
        pg_client.get(
            "/api/v1/compliance/assessments",
            headers=owner_headers,
            params={"organization_id": organization_id, "page_size": 101},
        ).status_code
        == 422
    )
    assert (
        pg_client.get(
            "/api/v1/compliance/summary",
            headers=owner_headers,
            params={"organization_id": organization_id, "aws_account_id": account_id},
        ).json()["assessments_total"]
        == 4
    )
    with pg_sessions.begin() as db:
        active = ComplianceAssessment(
            organization_id=uuid.UUID(organization_id),
            aws_account_id=uuid.UUID(account_id),
            framework_id=uuid.UUID(framework["id"]),
            status=ComplianceAssessmentStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        db.add(active)
        db.flush()
        active_id = active.id
    conflict = pg_client.post(
        f"/api/v1/aws/accounts/{account_id}/compliance/assess",
        headers=owner_headers,
        json={"framework_key": framework["key"]},
    )
    assert conflict.status_code == 409
    with pg_sessions.begin() as db:
        loaded_active = db.get(ComplianceAssessment, active_id)
        assert loaded_active is not None
        db.delete(loaded_active)

    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            params={"organization_id": organization_id},
        ).status_code
        == 401
    )
    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            headers={"Authorization": "Bearer malformed"},
            params={"organization_id": organization_id},
        ).status_code
        == 401
    )
    no_membership_email = f"stage5-no-membership-{marker}@example.com"
    no_membership_headers = register_and_login(pg_client, no_membership_email)
    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            headers=no_membership_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
    with pg_sessions() as db:
        no_membership_user = db.scalar(
            select(User).where(User.normalized_email == no_membership_email)
        )
        assert no_membership_user is not None
        expired_token = create_access_token(
            no_membership_user.id,
            get_settings(),
            datetime.now(UTC) - timedelta(hours=2),
        )
    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            headers={"Authorization": f"Bearer {expired_token}"},
            params={"organization_id": organization_id},
        ).status_code
        == 401
    )

    other_headers = register_and_login(pg_client, f"stage5-other-owner-{marker}@example.com")
    other_organization = pg_client.post(
        "/api/v1/organizations",
        headers=other_headers,
        json={"name": "Other tenant", "slug": f"stage5-other-http-{marker}"},
    ).json()["id"]
    other_account = pg_client.post(
        "/api/v1/aws/accounts",
        headers=other_headers,
        json={
            "organization_id": other_organization,
            "name": "Other account",
            "account_id": str((uuid.uuid4().int + 1) % 1_000_000_000_000).zfill(12),
        },
    ).json()["account"]["id"]
    assert (
        pg_client.post(
            f"/api/v1/aws/accounts/{other_account}/compliance/assess",
            headers=owner_headers,
            json={"framework_key": framework["key"]},
        ).status_code
        == 404
    )
    other_assessment = pg_client.post(
        f"/api/v1/aws/accounts/{other_account}/compliance/assess",
        headers=other_headers,
        json={"framework_key": framework["key"], "framework_version": framework["version"]},
    )
    assert other_assessment.status_code == 201
    other_assessment_id = other_assessment.json()["id"]
    other_detail = pg_client.get(
        f"/api/v1/compliance/assessments/{other_assessment_id}",
        headers=other_headers,
        params={"organization_id": other_organization},
    )
    assert other_detail.status_code == 200
    other_snapshot_id = other_detail.json()["controls"][0]["id"]
    assert (
        pg_client.get(
            f"/api/v1/compliance/assessments/{other_assessment_id}",
            headers=owner_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
    assert (
        pg_client.get(
            f"/api/v1/compliance/assessments/{other_assessment_id}/controls/{other_snapshot_id}",
            headers=owner_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )

    def fail_assessment(*_args: Any, **_kwargs: Any) -> ComplianceAssessment:
        raise RuntimeError("provider-secret-must-not-escape")

    monkeypatch.setattr(ComplianceService, "assess", fail_assessment)
    with (
        caplog.at_level("ERROR", logger="app.api.v1.compliance"),
        TestClient(app, base_url="http://testserver", raise_server_exceptions=False) as safe,
    ):
        failed_response = safe.post(
            f"/api/v1/aws/accounts/{account_id}/compliance/assess",
            headers=owner_headers,
            json={"framework_key": framework["key"]},
        )
    assert failed_response.status_code == 500
    assert "provider-secret-must-not-escape" not in failed_response.text
    assert "provider-secret-must-not-escape" not in caplog.text
    with pg_sessions() as db:
        failed_audit = db.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == uuid.UUID(organization_id),
                AuditEvent.event_type == "compliance.assessment.failed",
            )
            .order_by(AuditEvent.created_at.desc())
        )
        assert failed_audit is not None
        assert failed_audit.metadata_json["error_code"] == "assessment_calculation_failed"
        assert "provider-secret-must-not-escape" not in str(failed_audit.metadata_json)
    assert (
        pg_client.get(
            f"/api/v1/compliance/assessments/{uuid.uuid4()}",
            headers=owner_headers,
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )

    viewer_email = f"stage5-http-{OrganizationRole.VIEWER.value}-{marker}@example.com"
    with pg_sessions.begin() as db:
        viewer = db.scalar(select(User).where(User.normalized_email == viewer_email))
        assert viewer is not None
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == uuid.UUID(organization_id),
                OrganizationMembership.user_id == viewer.id,
            )
        )
        assert membership is not None
        membership.status = MembershipStatus.SUSPENDED
    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            headers=role_headers[OrganizationRole.VIEWER],
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )
    with pg_sessions.begin() as db:
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == uuid.UUID(organization_id),
                OrganizationMembership.user_id == viewer.id,
            )
        )
        assert membership is not None
        membership.status = MembershipStatus.REMOVED
    assert (
        pg_client.get(
            "/api/v1/compliance/frameworks",
            headers=role_headers[OrganizationRole.VIEWER],
            params={"organization_id": organization_id},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("failure_point", ["after_apply", "completion_audit", "final_commit"])
def test_postgres_stage4_finalization_rolls_back_all_persistence_and_retries_cleanly(
    pg_sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    with pg_sessions() as db:
        user, organization, account, _asset = _evaluable_account(db, f"atomic-{failure_point}")
        db.commit()
        ids = user.id, organization.id, account.id
    user_id, organization_id, account_id = ids

    with pg_sessions() as db:
        actor = db.get(User, user_id)
        assert actor is not None
        service = EvaluationService(db)
        restore: tuple[object, str, Any] | None = None
        if failure_point == "after_apply":
            original_apply = service._apply_result
            raised = False

            def fail_after_apply(*args: Any, **kwargs: Any) -> None:
                nonlocal raised
                original_apply(*args, **kwargs)
                if not raised:
                    raised = True
                    raise RuntimeError("controlled_after_apply_failure")

            monkeypatch.setattr(service, "_apply_result", fail_after_apply)
        elif failure_point == "completion_audit":
            original_audit = cast(Any, evaluations_module).record_audit

            def fail_completion_audit(
                session: Session, event_type: str, *args: Any, **kwargs: Any
            ) -> AuditEvent:
                if event_type == "security.evaluation.completed":
                    raise RuntimeError("controlled_completion_audit_failure")
                return cast(AuditEvent, original_audit(session, event_type, *args, **kwargs))

            monkeypatch.setattr(evaluations_module, "record_audit", fail_completion_audit)
            restore = (evaluations_module, "record_audit", original_audit)
        else:
            original_commit = db.commit
            commit_count = 0

            def fail_final_commit() -> None:
                nonlocal commit_count
                commit_count += 1
                if commit_count == 3:
                    raise RuntimeError("controlled_final_commit_failure")
                original_commit()

            monkeypatch.setattr(db, "commit", fail_final_commit)
            restore = (db, "commit", original_commit)

        failed = service.start(account_id, actor)
        assert failed.status == EvaluationJobStatus.FAILED
        failed_id = failed.id
        if restore is not None:
            target, name, value = restore
            monkeypatch.setattr(target, name, value)

    with pg_sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(EvaluationRuleResult)
                .where(EvaluationRuleResult.evaluation_job_id == failed_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Finding)
                .where(Finding.aws_account_id == account_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.resource_id == failed_id,
                    AuditEvent.event_type == "security.evaluation.completed",
                )
            )
            == 0
        )
        actor = db.get(User, user_id)
        assert actor is not None
        retried = EvaluationService(db).start(account_id, actor)
        assert retried.status == EvaluationJobStatus.COMPLETED
        result_count = db.scalar(
            select(func.count())
            .select_from(EvaluationRuleResult)
            .where(EvaluationRuleResult.evaluation_job_id == retried.id)
        )
        assert result_count is not None and result_count > 0
        assert retried.organization_id == organization_id


def test_postgres_stage5_assessments_use_persisted_stage4_evidence_and_remain_immutable(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant_account(db, "semantic-integration")
        _active_member(db, user, organization)
        service = ComplianceService(db)
        service.ensure_catalog()
        framework = service.framework("cis_aws")
        mappings = list(
            db.scalars(
                select(RuleControlMapping).where(RuleControlMapping.framework_id == framework.id)
            ).all()
        )
        rule_keys = sorted({mapping.rule_key for mapping in mappings})
        passing_evaluation = _evaluation(
            db,
            user,
            organization,
            account,
            sequence=1,
            status=EvaluationJobStatus.RUNNING,
            rules_evaluated=len(rule_keys),
            passed_count=len(rule_keys),
        )
        for rule_key in rule_keys:
            db.add(
                EvaluationRuleResult(
                    evaluation_job_id=passing_evaluation.id,
                    organization_id=organization.id,
                    aws_account_id=account.id,
                    rule_key=rule_key,
                    rule_version=1,
                    passed_count=1,
                    failed_count=0,
                    not_applicable_count=0,
                    error_count=0,
                )
            )
        db.flush()
        passing_evaluation.status = EvaluationJobStatus.COMPLETED
        passing_evaluation.finished_at = datetime.now(UTC)
        db.commit()

        first = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, passing_evaluation.id
        )
        assert first.controls_passed == first.controls_total
        original_snapshots = {
            row.id: (row.status, row.findings_count)
            for row in db.scalars(
                select(ComplianceAssessmentControl).where(
                    ComplianceAssessmentControl.assessment_id == first.id
                )
            ).all()
        }

        now = datetime.now(UTC)
        finding = Finding(
            organization_id=organization.id,
            aws_account_id=account.id,
            rule_key=rule_keys[0],
            rule_version=1,
            severity=FindingSeverity.CRITICAL,
            category="network",
            status=FindingStatus.OPEN,
            evidence_json={"source": "postgres-integration"},
            first_seen_at=now,
            last_seen_at=now,
            last_evaluation_id=passing_evaluation.id,
        )
        db.add(finding)
        db.commit()
        failed = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, passing_evaluation.id
        )
        assert failed.controls_failed > 0

        finding.status = FindingStatus.SUPPRESSED
        finding.suppressed_at = datetime.now(UTC)
        finding.suppression_reason = "Approved but still noncompliant"
        finding.suppressed_by_user_id = user.id
        db.commit()
        suppressed = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, passing_evaluation.id
        )
        assert suppressed.controls_failed > 0

        finding.status = FindingStatus.RESOLVED
        finding.resolved_at = datetime.now(UTC)
        finding.suppressed_at = None
        finding.suppression_reason = None
        finding.suppressed_by_user_id = None
        db.commit()
        resolved = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, passing_evaluation.id
        )
        assert resolved.controls_passed == resolved.controls_total

        error_evaluation = _evaluation(
            db,
            user,
            organization,
            account,
            sequence=2,
            status=EvaluationJobStatus.RUNNING,
            rules_evaluated=len(rule_keys),
            passed_count=len(rule_keys) - 1,
            error_count=1,
        )
        for index, rule_key in enumerate(rule_keys):
            db.add(
                EvaluationRuleResult(
                    evaluation_job_id=error_evaluation.id,
                    organization_id=organization.id,
                    aws_account_id=account.id,
                    rule_key=rule_key,
                    rule_version=1,
                    passed_count=0 if index == 0 else 1,
                    failed_count=0,
                    not_applicable_count=0,
                    error_count=1 if index == 0 else 0,
                )
            )
        db.flush()
        error_evaluation.status = EvaluationJobStatus.COMPLETED
        error_evaluation.finished_at = datetime.now(UTC)
        db.commit()
        errored = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, error_evaluation.id
        )
        assert errored.controls_error > 0
        assert errored.controls_passed == 0

        legacy = _evaluation(
            db,
            user,
            organization,
            account,
            sequence=3,
            rules_evaluated=len(rule_keys),
            passed_count=len(rule_keys),
        )
        db.commit()
        legacy_assessment = ComplianceService(db).assess(
            account.id, user, framework.key, framework.version, legacy.id
        )
        assert legacy_assessment.controls_not_assessed == legacy_assessment.controls_total
        assert legacy_assessment.controls_passed == 0

        persisted_original = {
            row.id: (row.status, row.findings_count)
            for row in db.scalars(
                select(ComplianceAssessmentControl).where(
                    ComplianceAssessmentControl.assessment_id == first.id
                )
            ).all()
        }
        assert persisted_original == original_snapshots
