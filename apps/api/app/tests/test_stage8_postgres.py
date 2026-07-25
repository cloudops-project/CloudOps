from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import (
    AccountRiskSnapshot,
    AIRequest,
    AIRequestSource,
    AIResponse,
    AIUsageWindow,
    Asset,
    AuditEvent,
    AWSAccount,
    ComplianceAssessment,
    ComplianceFramework,
    DiscoveryJob,
    EvaluationJob,
    Finding,
    Organization,
    OrganizationMembership,
    OrganizationRiskSnapshot,
    RiskAssessment,
    RiskScoringPolicy,
    User,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    ComplianceAssessmentStatus,
    DiscoveryJobStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    MembershipStatus,
    OrganizationRole,
    RiskAssessmentStatus,
    RiskPriority,
)
from app.security.tokens import create_access_token

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test" or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError("Stage 8A PostgreSQL tests require a disposable CloudOps test database.")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 8A PostgreSQL integrity tests",
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


def test_postgres_dialect_is_selected(pg_sessions: sessionmaker[Session]) -> None:
    """Proves the test process is actually bound to PostgreSQL, not SQLite."""
    with pg_sessions() as db:
        engine = db.get_bind()
        assert isinstance(engine, Engine)
        assert engine.dialect.name == "postgresql"
        version = db.execute(select(func.version())).scalar_one()
        assert "PostgreSQL" in version


def _headers(user: User, *, expired: bool = False) -> dict[str, str]:
    now = datetime(2020, 1, 1, tzinfo=UTC) if expired else None
    return {"Authorization": f"Bearer {create_access_token(user.id, get_settings(), now=now)}"}


def _user(db: Session, marker: str) -> User:
    user = User(
        email=f"{marker}-{uuid.uuid4().hex[:10]}@example.com",
        normalized_email=f"{marker}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="test-only-hash",
        full_name=f"{marker} User",
    )
    db.add(user)
    db.flush()
    return user


def _organization(db: Session, owner: User, marker: str) -> Organization:
    org = Organization(
        name=f"Dashboard PG {marker}",
        slug=f"dashboard-pg-{marker}-{uuid.uuid4().hex[:10]}",
        created_by_user_id=owner.id,
    )
    db.add(org)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=org.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.flush()
    return org


def _member(
    db: Session,
    organization: Organization,
    role: OrganizationRole,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> User:
    user = _user(db, f"dashboard-pg-{role.value}-{status.value}")
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            status=status,
        )
    )
    db.flush()
    return user


def _account(
    db: Session,
    organization: Organization,
    user: User,
    marker: str,
    *,
    connection_status: AWSAccountStatus = AWSAccountStatus.CONNECTED,
) -> AWSAccount:
    account = AWSAccount(
        organization_id=organization.id,
        name=f"Account {marker}",
        account_id=str(uuid.uuid4().int % 1_000_000_000_000).zfill(12),
        external_id=f"dashboard-pg-{marker}-{uuid.uuid4().hex}",
        status=connection_status,
        connection_status=connection_status,
        created_by_user_id=user.id,
    )
    db.add(account)
    db.flush()
    return account


def _asset(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    marker: str,
    *,
    asset_type: AssetType,
    region: str,
    active: bool = True,
) -> Asset:
    now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    asset = Asset(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_type=asset_type,
        resource_id=f"asset-{marker}-{uuid.uuid4().hex[:8]}",
        name=f"Asset {marker}",
        region=region,
        is_active=active,
        metadata_json={"test": "dashboard-pg", "secret": "must-not-leak"},
        first_seen_at=now - timedelta(days=2),
        last_seen_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def _evaluation(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    user: User,
    *,
    sequence: int,
    status: EvaluationJobStatus = EvaluationJobStatus.COMPLETED,
) -> EvaluationJob:
    now = datetime(2026, 7, 25, 12, sequence, tzinfo=UTC)
    job = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account.id,
        sequence=sequence,
        status=status,
        started_by_user_id=user.id,
        started_at=now - timedelta(minutes=5) if status != EvaluationJobStatus.PENDING else None,
        finished_at=now
        if status
        in {
            EvaluationJobStatus.COMPLETED,
            EvaluationJobStatus.PARTIALLY_COMPLETED,
            EvaluationJobStatus.FAILED,
        }
        else None,
    )
    db.add(job)
    db.flush()
    return job


def _finding(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    asset: Asset,
    evaluation: EvaluationJob,
    marker: str,
    *,
    severity: FindingSeverity,
    status: FindingStatus = FindingStatus.OPEN,
    category: str = "network",
    last_seen_offset: int = 0,
) -> Finding:
    now = datetime(2026, 7, 25, 13, 0, tzinfo=UTC) + timedelta(minutes=last_seen_offset)
    kwargs: dict[str, Any] = {}
    if status == FindingStatus.SUPPRESSED:
        kwargs = {
            "suppressed_at": now,
            "suppression_reason": "Dashboard PG suppression fixture",
            "suppressed_by_user_id": evaluation.started_by_user_id,
        }
    if status == FindingStatus.RESOLVED:
        kwargs = {"resolved_at": now}
    finding = Finding(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_id=asset.id,
        rule_key=f"{category.upper()}_{marker}_{uuid.uuid4().hex[:6]}",
        rule_version=1,
        severity=severity,
        category=category,
        status=status,
        evidence_json={"raw": "sensitive-dashboard-pg-evidence"},
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        last_evaluation_id=evaluation.id,
        lifecycle_version=1,
        **kwargs,
    )
    db.add(finding)
    db.flush()
    return finding


def _compliance(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    *,
    finished_at: datetime,
    status: ComplianceAssessmentStatus = ComplianceAssessmentStatus.COMPLETED,
) -> ComplianceAssessment:
    framework = ComplianceFramework(
        key=f"dash-pg-{uuid.uuid4().hex[:10]}",
        name="Dashboard PG Framework",
        version="1.0",
        description="Dashboard PostgreSQL fixture framework.",
        official_reference="https://example.invalid/dashboard-pg",
    )
    db.add(framework)
    db.flush()
    assessment = ComplianceAssessment(
        organization_id=organization.id,
        aws_account_id=account.id,
        framework_id=framework.id,
        status=status,
        controls_total=10 if status == ComplianceAssessmentStatus.COMPLETED else 0,
        controls_passed=7 if status == ComplianceAssessmentStatus.COMPLETED else 0,
        controls_failed=2 if status == ComplianceAssessmentStatus.COMPLETED else 0,
        controls_not_assessed=1 if status == ComplianceAssessmentStatus.COMPLETED else 0,
        controls_error=0,
        findings_count=2,
        started_at=finished_at - timedelta(minutes=10)
        if status != ComplianceAssessmentStatus.PENDING
        else None,
        finished_at=finished_at
        if status in {ComplianceAssessmentStatus.COMPLETED, ComplianceAssessmentStatus.FAILED}
        else None,
    )
    db.add(assessment)
    db.flush()
    return assessment


def _risk(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    user: User,
    *,
    evaluation_time: datetime,
    score: int,
    status: RiskAssessmentStatus = RiskAssessmentStatus.COMPLETED,
) -> RiskAssessment:
    policy = db.scalar(
        select(RiskScoringPolicy).where(RiskScoringPolicy.key == "DASHBOARD_PG_TEST")
    )
    if policy is None:
        policy = RiskScoringPolicy(
            key="DASHBOARD_PG_TEST",
            version=1,
            name="Dashboard PG test policy",
            description="Dashboard PostgreSQL fixture policy.",
            weights_json={},
            bands_json={},
        )
        db.add(policy)
        db.flush()
    assessment = RiskAssessment(
        organization_id=organization.id,
        aws_account_id=None,
        policy_id=policy.id,
        evaluation_time=evaluation_time,
        source_cutoff_at=evaluation_time,
        status=status,
        started_by_user_id=user.id,
        started_at=evaluation_time - timedelta(minutes=3)
        if status != RiskAssessmentStatus.PENDING
        else None,
        finished_at=evaluation_time
        if status in {RiskAssessmentStatus.COMPLETED, RiskAssessmentStatus.FAILED}
        else None,
        findings_total=5 if status == RiskAssessmentStatus.COMPLETED else 0,
        critical_count=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        high_count=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        medium_count=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        low_count=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        informational_count=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        accounts_scored=1 if status == RiskAssessmentStatus.COMPLETED else 0,
        aggregate_score=score if status == RiskAssessmentStatus.COMPLETED else None,
        aggregate_priority=RiskPriority.HIGH if status == RiskAssessmentStatus.COMPLETED else None,
    )
    db.add(assessment)
    db.flush()
    if status == RiskAssessmentStatus.COMPLETED:
        db.add(
            OrganizationRiskSnapshot(
                assessment_id=assessment.id,
                organization_id=organization.id,
                evaluation_time=evaluation_time,
                risk_score=score,
                priority=RiskPriority.HIGH,
                highest_account_score=score,
                mean_account_score=score,
                accounts_total=1,
                reason_code="dashboard_pg_fixture",
            )
        )
        db.add(
            AccountRiskSnapshot(
                assessment_id=assessment.id,
                organization_id=organization.id,
                aws_account_id=account.id,
                evaluation_time=evaluation_time,
                risk_score=score,
                priority=RiskPriority.HIGH,
                highest_finding_score=score,
                top_ten_mean=score,
                all_findings_mean=score,
                findings_total=5,
            )
        )
        db.flush()
    return assessment


def _seed_dashboard_org(db: Session) -> tuple[User, Organization]:
    owner = _user(db, "dashboard-pg-owner")
    org = _organization(db, owner, "primary")
    connected = _account(db, org, owner, "connected", connection_status=AWSAccountStatus.CONNECTED)
    _account(db, org, owner, "failed", connection_status=AWSAccountStatus.FAILED)
    first_asset = _asset(
        db, org, connected, "primary", asset_type=AssetType.EC2_SECURITY_GROUP, region="us-east-1"
    )
    _asset(
        db,
        org,
        connected,
        "secondary",
        asset_type=AssetType.S3_BUCKET,
        region="us-west-2",
        active=False,
    )
    evaluation = _evaluation(db, org, connected, owner, sequence=1)
    _finding(
        db,
        org,
        connected,
        first_asset,
        evaluation,
        "critical",
        severity=FindingSeverity.CRITICAL,
        category="network",
        last_seen_offset=2,
    )
    _finding(
        db,
        org,
        connected,
        first_asset,
        evaluation,
        "high",
        severity=FindingSeverity.HIGH,
        category="identity",
        last_seen_offset=1,
    )
    _finding(
        db,
        org,
        connected,
        first_asset,
        evaluation,
        "medium",
        severity=FindingSeverity.MEDIUM,
        category="network",
    )
    _finding(
        db,
        org,
        connected,
        first_asset,
        evaluation,
        "resolved",
        severity=FindingSeverity.LOW,
        status=FindingStatus.RESOLVED,
    )
    _finding(
        db,
        org,
        connected,
        first_asset,
        evaluation,
        "suppressed",
        severity=FindingSeverity.CRITICAL,
        status=FindingStatus.SUPPRESSED,
    )
    db.add(
        DiscoveryJob(
            organization_id=org.id,
            aws_account_id=connected.id,
            status=DiscoveryJobStatus.COMPLETED,
            started_by_user_id=owner.id,
            started_at=datetime(2026, 7, 25, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 25, 10, 5, tzinfo=UTC),
        )
    )
    _compliance(db, org, connected, finished_at=datetime(2026, 7, 25, 11, 0, tzinfo=UTC))
    _compliance(
        db,
        org,
        connected,
        finished_at=datetime(2026, 7, 25, 11, 30, tzinfo=UTC),
        status=ComplianceAssessmentStatus.FAILED,
    )
    _risk(
        db,
        org,
        connected,
        owner,
        evaluation_time=datetime(2026, 7, 25, 11, 30, tzinfo=UTC),
        score=60,
    )
    _risk(
        db,
        org,
        connected,
        owner,
        evaluation_time=datetime(2026, 7, 25, 12, 30, tzinfo=UTC),
        score=72,
    )
    _risk(
        db,
        org,
        connected,
        owner,
        evaluation_time=datetime(2026, 7, 25, 13, 30, tzinfo=UTC),
        score=0,
        status=RiskAssessmentStatus.FAILED,
    )
    db.commit()
    return owner, org


def _dashboard(client: TestClient, user: User, organization: Organization) -> dict[str, Any]:
    response = client.get(
        "/api/v1/dashboard/summary",
        headers=_headers(user),
        params={"organization_id": str(organization.id)},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_postgres_dashboard_auth_missing_malformed_expired_token(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner, org = _seed_dashboard_org(db)
        org_id = org.id

    assert pg_client.get("/api/v1/dashboard/summary").status_code == 401
    assert (
        pg_client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": "Bearer malformed"},
            params={"organization_id": str(org_id)},
        ).status_code
        == 401
    )
    assert (
        pg_client.get(
            "/api/v1/dashboard/summary",
            headers=_headers(owner, expired=True),
            params={"organization_id": str(org_id)},
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------
# Membership: active, absent, removed, suspended
# ---------------------------------------------------------------------------


def test_postgres_dashboard_membership_absent_removed_suspended(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner, org = _seed_dashboard_org(db)
        absent_user = _user(db, "dashboard-pg-absent")
        suspended_user = _member(
            db, org, OrganizationRole.VIEWER, status=MembershipStatus.SUSPENDED
        )
        removed_user = _member(db, org, OrganizationRole.VIEWER, status=MembershipStatus.REMOVED)
        db.commit()
        org_id = org.id
        for user in (absent_user, suspended_user, removed_user):
            response = pg_client.get(
                "/api/v1/dashboard/summary",
                headers=_headers(user),
                params={"organization_id": str(org_id)},
            )
            assert response.status_code == 404

        response = pg_client.get(
            "/api/v1/dashboard/summary",
            headers=_headers(owner),
            params={"organization_id": str(org_id)},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Six roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.SECURITY_ANALYST,
        OrganizationRole.CLOUD_ENGINEER,
        OrganizationRole.AUDITOR,
        OrganizationRole.VIEWER,
    ],
)
def test_postgres_dashboard_all_six_active_roles_can_read(
    pg_client: TestClient, pg_sessions: sessionmaker[Session], role: OrganizationRole
) -> None:
    with pg_sessions() as db:
        owner, org = _seed_dashboard_org(db)
        user = owner if role == OrganizationRole.OWNER else _member(db, org, role)
        db.commit()
        org_id = org.id
        response = pg_client.get(
            "/api/v1/dashboard/summary",
            headers=_headers(user),
            params={"organization_id": str(org_id)},
        )
        assert response.status_code == 200, response.text
        assert response.json()["metadata"]["organization_id"] == str(org_id)


# ---------------------------------------------------------------------------
# Tenant isolation across at least two organizations
# ---------------------------------------------------------------------------


def test_postgres_dashboard_tenant_isolation_across_two_organizations(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner_a, org_a = _seed_dashboard_org(db)

        owner_b = _user(db, "dashboard-pg-tenant-b-owner")
        org_b = _organization(db, owner_b, "tenant-b")
        account_b = _account(db, org_b, owner_b, "tenant-b-account")
        asset_b = _asset(
            db,
            org_b,
            account_b,
            "tenant-b-asset",
            asset_type=AssetType.RDS_INSTANCE,
            region="eu-west-1",
        )
        evaluation_b = _evaluation(db, org_b, account_b, owner_b, sequence=1)
        _finding(
            db,
            org_b,
            account_b,
            asset_b,
            evaluation_b,
            "tenant-b-critical",
            severity=FindingSeverity.CRITICAL,
            category="network",
        )
        _compliance(db, org_b, account_b, finished_at=datetime(2026, 7, 25, 11, 0, tzinfo=UTC))
        _risk(
            db,
            org_b,
            account_b,
            owner_b,
            evaluation_time=datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
            score=90,
        )
        db.commit()
        org_a_id, org_b_id = org_a.id, org_b.id

    payload_a = _dashboard(pg_client, owner_a, org_a)
    payload_b = _dashboard(pg_client, owner_b, org_b)

    # Tenant A totals must equal the fixture seeded only for A, unaffected by B's data.
    assert payload_a["accounts"]["total_accounts"] == 2
    assert payload_a["assets"]["total_assets"] == 2
    assert payload_a["findings"]["open_total"] == 3
    assert payload_a["compliance"]["controls_total"] == 10
    assert payload_a["risk"]["aggregate_score"] == 72
    assert len(payload_a["account_risk_heatmap"]) == 1
    assert payload_a["account_risk_heatmap"][0]["score"] == 72
    assert len(payload_a["risk"]["trend"]) == 2
    assert payload_a["freshness"]["latest_completed_discovery"] is not None

    # Tenant B totals reflect only B's fixture, proving no cross-tenant leakage either direction.
    assert payload_b["accounts"]["total_accounts"] == 1
    assert payload_b["assets"]["total_assets"] == 1
    assert payload_b["findings"]["open_total"] == 1
    assert payload_b["compliance"]["controls_total"] == 10
    assert payload_b["risk"]["aggregate_score"] == 90
    assert len(payload_b["account_risk_heatmap"]) == 1
    assert payload_b["account_risk_heatmap"][0]["score"] == 90
    assert len(payload_b["risk"]["trend"]) == 1
    # B has no discovery job seeded, proving freshness section is also tenant scoped.
    assert payload_b["freshness"]["latest_completed_discovery"] is None
    assert org_a_id != org_b_id


# ---------------------------------------------------------------------------
# Exact aggregation
# ---------------------------------------------------------------------------


def test_postgres_dashboard_exact_aggregation(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner, org = _seed_dashboard_org(db)

    payload = _dashboard(pg_client, owner, org)

    assert payload["accounts"] == {
        "total_accounts": 2,
        "connected_accounts": 1,
        "disconnected_accounts": 0,
        "accounts_requiring_attention": 1,
    }
    assert payload["assets"]["total_assets"] == 2
    assert payload["assets"]["active_assets"] == 1
    assert payload["assets"]["inactive_assets"] == 1
    assert payload["assets"]["counts_by_type"] == [
        {"key": "ec2_security_group", "count": 1},
        {"key": "s3_bucket", "count": 1},
    ]
    assert payload["assets"]["counts_by_region"] == [
        {"key": "us-east-1", "count": 1},
        {"key": "us-west-2", "count": 1},
    ]
    assert payload["findings"]["open_total"] == 3
    assert payload["findings"]["resolved_total"] == 1
    assert payload["findings"]["suppressed_total"] == 1
    assert payload["findings"]["open_by_severity"] == [
        {"key": "critical", "count": 1},
        {"key": "high", "count": 1},
        {"key": "medium", "count": 1},
    ]
    assert payload["findings"]["open_by_service"] == [
        {"key": "network", "count": 2},
        {"key": "identity", "count": 1},
    ]
    recent = payload["findings"]["recent_critical_and_high_findings"]
    assert [item["severity"] for item in recent] == ["critical", "high"]
    assert len(recent) <= 10
    assert payload["compliance"]["controls_total"] == 10
    assert payload["compliance"]["passed"] == 7
    assert payload["compliance"]["pass_percentage"] == 70.0
    assert payload["risk"]["aggregate_score"] == 72
    assert payload["risk"]["aggregate_priority"] == "high"
    assert [point["aggregate_score"] for point in payload["risk"]["trend"]] == [60, 72]
    assert payload["account_risk_heatmap"][0]["score"] == 72
    assert payload["account_risk_heatmap"][0]["critical_count"] == 1
    assert payload["account_risk_heatmap"][0]["high_count"] == 1
    assert payload["freshness"]["latest_completed_discovery"]["status"] == "completed"
    assert payload["freshness"]["latest_risk_assessment"]["status"] == "failed"
    assert payload["metadata"]["is_partial"] is False
    assert payload["metadata"]["missing_sections"] == []


# ---------------------------------------------------------------------------
# Empty and partial states
# ---------------------------------------------------------------------------


def test_postgres_dashboard_empty_and_partial_states(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner = _user(db, "dashboard-pg-empty-owner")
        org = _organization(db, owner, "empty")
        db.commit()
        org_id = org.id

    payload = _dashboard(pg_client, owner, org)
    assert payload["metadata"]["is_partial"] is True
    assert payload["metadata"]["missing_sections"] == [
        "accounts",
        "assets",
        "findings",
        "latest_completed_compliance_assessment",
        "latest_completed_risk_assessment",
        "latest_completed_discovery",
        "latest_completed_evaluation",
    ]
    assert payload["compliance"]["assessment_id"] is None
    assert payload["risk"]["assessment_id"] is None

    with pg_sessions() as db2:
        org_reloaded = db2.get(Organization, org_id)
        assert org_reloaded is not None
        account = _account(
            db2, org_reloaded, owner, "partial", connection_status=AWSAccountStatus.PENDING
        )
        _asset(
            db2,
            org_reloaded,
            account,
            "partial",
            asset_type=AssetType.IAM_ROLE,
            region="",
            active=True,
        )
        db2.commit()

    partial = _dashboard(pg_client, owner, org)
    assert partial["accounts"]["total_accounts"] == 1
    assert partial["assets"]["total_assets"] == 1
    assert "accounts" not in partial["metadata"]["missing_sections"]
    assert "latest_completed_compliance_assessment" in partial["metadata"]["missing_sections"]


def test_postgres_dashboard_running_and_failed_latest_assessment_falls_back_to_completed(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner = _user(db, "dashboard-pg-fallback-owner")
        org = _organization(db, owner, "fallback")
        account = _account(db, org, owner, "fallback-account")
        _compliance(
            db,
            org,
            account,
            finished_at=datetime(2026, 7, 25, 9, 0, tzinfo=UTC),
            status=ComplianceAssessmentStatus.COMPLETED,
        )
        # A newer RUNNING assessment must not be selected over the older COMPLETED one.
        running = ComplianceFramework(
            key=f"dash-pg-running-{uuid.uuid4().hex[:8]}",
            name="Running Framework",
            version="1.0",
            description="Running fixture.",
            official_reference="https://example.invalid/running",
        )
        db.add(running)
        db.flush()
        db.add(
            ComplianceAssessment(
                organization_id=org.id,
                aws_account_id=account.id,
                framework_id=running.id,
                status=ComplianceAssessmentStatus.RUNNING,
                controls_total=0,
                controls_passed=0,
                controls_failed=0,
                controls_not_assessed=0,
                controls_error=0,
                findings_count=0,
                started_at=datetime(2026, 7, 25, 10, 0, tzinfo=UTC),
            )
        )
        db.commit()
        org_ref = org

    payload = _dashboard(pg_client, owner, org_ref)
    assert payload["compliance"]["controls_total"] == 10
    assert payload["compliance"]["assessment_status"] == "completed"


def test_postgres_dashboard_resolved_suppressed_only_findings(
    pg_client: TestClient, pg_sessions: sessionmaker[Session]
) -> None:
    with pg_sessions() as db:
        owner = _user(db, "dashboard-pg-resolved-owner")
        org = _organization(db, owner, "resolved-only")
        account = _account(db, org, owner, "resolved-account")
        asset = _asset(
            db,
            org,
            account,
            "resolved-asset",
            asset_type=AssetType.EC2_INSTANCE,
            region="us-east-1",
        )
        evaluation = _evaluation(db, org, account, owner, sequence=1)
        _finding(
            db,
            org,
            account,
            asset,
            evaluation,
            "resolved-only",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.RESOLVED,
        )
        _finding(
            db,
            org,
            account,
            asset,
            evaluation,
            "suppressed-only",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.SUPPRESSED,
        )
        db.commit()
        org_ref = org

    payload = _dashboard(pg_client, owner, org_ref)
    assert payload["findings"]["open_total"] == 0
    assert payload["findings"]["resolved_total"] == 1
    assert payload["findings"]["suppressed_total"] == 1
    assert payload["findings"]["open_by_severity"] == []
    assert payload["findings"]["recent_critical_and_high_findings"] == []
    assert "findings" not in payload["metadata"]["missing_sections"]


# ---------------------------------------------------------------------------
# No-mutation proof
# ---------------------------------------------------------------------------

_CANONICAL_TABLES = [
    User,
    Organization,
    OrganizationMembership,
    AWSAccount,
    Asset,
    DiscoveryJob,
    EvaluationJob,
    Finding,
    ComplianceAssessment,
    RiskAssessment,
    AIRequest,
    AIRequestSource,
    AIResponse,
    AIUsageWindow,
    AuditEvent,
]


def test_postgres_dashboard_no_mutation_across_repeated_requests(
    pg_client: TestClient, pg_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pg_sessions() as db:
        owner, org = _seed_dashboard_org(db)
        org_ref = org
        owner_ref = owner

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dashboard must not call providers")

    monkeypatch.setattr("app.services.ai.MockAIProvider", lambda *_args, **_kwargs: forbidden)

    with pg_sessions() as counter:
        before = {
            table.__tablename__: int(counter.scalar(select(func.count()).select_from(table)) or 0)
            for table in _CANONICAL_TABLES
        }

    statements: list[str] = []

    with pg_sessions() as observed:
        engine = observed.get_bind()
        assert isinstance(engine, Engine)

        def before_cursor_execute(
            _conn: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        try:
            for _ in range(3):
                payload = _dashboard(pg_client, owner_ref, org_ref)
                assert len(payload["assets"]["counts_by_type"]) <= 10
                assert len(payload["findings"]["recent_critical_and_high_findings"]) <= 10
                assert len(payload["account_risk_heatmap"]) <= 20
                assert len(payload["risk"]["trend"]) <= 12
        finally:
            event.remove(engine, "before_cursor_execute", before_cursor_execute)

    with pg_sessions() as counter:
        after = {
            table.__tablename__: int(counter.scalar(select(func.count()).select_from(table)) or 0)
            for table in _CANONICAL_TABLES
        }

    assert after == before, f"canonical row counts changed: before={before} after={after}"

    joined_statements = "\n".join(statements).lower()
    assert "insert into" not in joined_statements
    assert "update " not in joined_statements
    assert "delete from" not in joined_statements


def test_postgres_dashboard_openapi_contract_present_once(pg_client: TestClient) -> None:
    openapi = pg_client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/dashboard/summary"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
