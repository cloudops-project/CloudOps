from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
        name=f"Dashboard {marker}",
        slug=f"dashboard-{marker}-{uuid.uuid4().hex[:10]}",
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
    user = _user(db, f"dashboard-{role.value}-{status.value}")
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
        external_id=f"dashboard-{marker}-{uuid.uuid4().hex}",
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
        metadata_json={"test": "dashboard", "secret": "must-not-leak"},
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
    kwargs = {}
    if status == FindingStatus.SUPPRESSED:
        kwargs = {
            "suppressed_at": now,
            "suppression_reason": "Dashboard suppression fixture",
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
        evidence_json={"raw": "sensitive-dashboard-evidence"},
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
        key=f"dash-{uuid.uuid4().hex[:10]}",
        name="Dashboard Framework",
        version="1.0",
        description="Dashboard fixture framework.",
        official_reference="https://example.invalid/dashboard",
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
    policy = db.scalar(select(RiskScoringPolicy).where(RiskScoringPolicy.key == "DASHBOARD_TEST"))
    if policy is None:
        policy = RiskScoringPolicy(
            key="DASHBOARD_TEST",
            version=1,
            name="Dashboard test policy",
            description="Dashboard fixture policy.",
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
                reason_code="dashboard_fixture",
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
    owner = _user(db, "dashboard-owner")
    org = _organization(db, owner, "primary")
    connected = _account(db, org, owner, "connected", connection_status=AWSAccountStatus.CONNECTED)
    _account(db, org, owner, "failed", connection_status=AWSAccountStatus.FAILED)
    first_asset = _asset(
        db,
        org,
        connected,
        "primary",
        asset_type=AssetType.EC2_SECURITY_GROUP,
        region="us-east-1",
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
    _compliance(
        db,
        org,
        connected,
        finished_at=datetime(2026, 7, 25, 11, 0, tzinfo=UTC),
    )
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
    other_owner = _user(db, "dashboard-other")
    other_org = _organization(db, other_owner, "other")
    other_account = _account(db, other_org, other_owner, "same-looking")
    other_asset = _asset(
        db,
        other_org,
        other_account,
        "other",
        asset_type=AssetType.RDS_INSTANCE,
        region="eu-west-1",
    )
    other_evaluation = _evaluation(db, other_org, other_account, other_owner, sequence=1)
    _finding(
        db,
        other_org,
        other_account,
        other_asset,
        other_evaluation,
        "other-critical",
        severity=FindingSeverity.CRITICAL,
        category="network",
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


def test_dashboard_summary_aggregates_authoritative_rows_and_excludes_tenant_data(
    client: TestClient, db: Session
) -> None:
    owner, org = _seed_dashboard_org(db)

    payload = _dashboard(client, owner, org)

    assert payload["metadata"]["organization_id"] == str(org.id)
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
    assert "sensitive-dashboard-evidence" not in json.dumps(payload)
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
def test_dashboard_all_six_active_roles_can_read(
    client: TestClient, db: Session, role: OrganizationRole
) -> None:
    owner, org = _seed_dashboard_org(db)
    user = owner if role == OrganizationRole.OWNER else _member(db, org, role)
    db.commit()

    response = client.get(
        "/api/v1/dashboard/summary",
        headers=_headers(user),
        params={"organization_id": str(org.id)},
    )

    assert response.status_code == 200, response.text


def test_dashboard_auth_membership_empty_and_partial_states(
    client: TestClient, db: Session
) -> None:
    owner = _user(db, "dashboard-empty-owner")
    org = _organization(db, owner, "empty")
    absent_user = _user(db, "dashboard-absent")
    suspended_user = _member(db, org, OrganizationRole.VIEWER, status=MembershipStatus.SUSPENDED)
    removed_user = _member(db, org, OrganizationRole.VIEWER, status=MembershipStatus.REMOVED)
    db.commit()

    assert client.get("/api/v1/dashboard/summary").status_code == 401
    assert (
        client.get(
            "/api/v1/dashboard/summary",
            headers={"Authorization": "Bearer malformed"},
            params={"organization_id": str(org.id)},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/dashboard/summary",
            headers=_headers(owner, expired=True),
            params={"organization_id": str(org.id)},
        ).status_code
        == 401
    )
    for user in (absent_user, suspended_user, removed_user):
        response = client.get(
            "/api/v1/dashboard/summary",
            headers=_headers(user),
            params={"organization_id": str(org.id)},
        )
        assert response.status_code == 404

    payload = _dashboard(client, owner, org)
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

    account = _account(db, org, owner, "partial", connection_status=AWSAccountStatus.PENDING)
    _asset(
        db,
        org,
        account,
        "partial",
        asset_type=AssetType.IAM_ROLE,
        region="",
        active=True,
    )
    db.commit()
    partial = _dashboard(client, owner, org)
    assert partial["accounts"]["total_accounts"] == 1
    assert partial["assets"]["total_assets"] == 1
    assert "accounts" not in partial["metadata"]["missing_sections"]
    assert "latest_completed_compliance_assessment" in partial["metadata"]["missing_sections"]


def test_dashboard_read_only_contract_openapi_and_bounded_query_count(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, org = _seed_dashboard_org(db)
    tables = [
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
    before = {
        table.__tablename__: int(db.scalar(select(func.count()).select_from(table)) or 0)
        for table in tables
    }
    calls = {"aws": 0, "ai": 0}

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dashboard must not call providers")

    monkeypatch.setattr("app.services.ai.MockAIProvider", lambda *_args, **_kwargs: forbidden)
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    statements: list[str] = []

    def before_cursor_execute(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if not statement.startswith("PRAGMA"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        for _ in range(2):
            payload = _dashboard(client, owner, org)
            assert len(payload["assets"]["counts_by_type"]) <= 10
            assert len(payload["findings"]["recent_critical_and_high_findings"]) <= 10
            assert len(payload["account_risk_heatmap"]) <= 20
            assert len(payload["risk"]["trend"]) <= 12
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    after = {
        table.__tablename__: int(db.scalar(select(func.count()).select_from(table)) or 0)
        for table in tables
    }
    assert after == before
    assert calls == {"aws": 0, "ai": 0}
    assert len(statements) <= 60
    joined_statements = "\n".join(statements).lower()
    assert "insert " not in joined_statements
    assert "update " not in joined_statements
    assert "delete " not in joined_statements

    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/dashboard/summary"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
