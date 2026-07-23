from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions.errors import ConflictError
from app.models import (
    Asset,
    AssetRiskContext,
    AuditEvent,
    AWSAccount,
    CompensatingControl,
    EvaluationJob,
    Finding,
    FindingRiskSnapshot,
    Organization,
    OrganizationMembership,
    RiskAssessment,
    User,
)
from app.models.enums import (
    AssetType,
    BusinessImpact,
    DataSensitivity,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    MembershipStatus,
    OrganizationRole,
    RiskCriticality,
    RiskEnvironment,
)
from app.security.tokens import create_access_token
from app.services.risk import RiskService


def _tenant(
    db: Session, role: OrganizationRole = OrganizationRole.OWNER
) -> tuple[User, Organization, AWSAccount]:
    marker = uuid.uuid4().hex
    user = User(
        email=f"risk-{marker}@example.com",
        normalized_email=f"risk-{marker}@example.com",
        password_hash="test-only-hash",
        full_name="Risk User",
    )
    db.add(user)
    db.flush()
    organization = Organization(
        name="Risk Organization",
        slug=f"risk-{marker}",
        created_by_user_id=user.id,
    )
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
    )
    account = AWSAccount(
        organization_id=organization.id,
        name="Risk Account",
        account_id=str(uuid.uuid4().int % 1_000_000_000_000).zfill(12),
        external_id=f"risk-{marker}",
        created_by_user_id=user.id,
    )
    db.add(account)
    db.flush()
    return user, organization, account


def _finding(
    db: Session,
    organization: Organization,
    account: AWSAccount,
    user: User,
    *,
    severity: FindingSeverity = FindingSeverity.CRITICAL,
    status: FindingStatus = FindingStatus.OPEN,
    rule_key: str = "EC2_SG_SSH_OPEN_TO_WORLD",
) -> tuple[Finding, Asset]:
    now = datetime(2026, 7, 24, tzinfo=UTC)
    asset = Asset(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id=f"sg-{uuid.uuid4().hex[:12]}",
        name="Internet security group",
        region="us-east-1",
        metadata_json={"publicly_accessible": True},
    )
    db.add(asset)
    db.flush()
    evaluation = EvaluationJob(
        organization_id=organization.id,
        aws_account_id=account.id,
        sequence=1,
        status=EvaluationJobStatus.COMPLETED,
        started_by_user_id=user.id,
        started_at=now - timedelta(minutes=1),
        finished_at=now,
    )
    db.add(evaluation)
    db.flush()
    finding = Finding(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_id=asset.id,
        rule_key=rule_key,
        rule_version=1,
        severity=severity,
        category="network",
        status=status,
        evidence_json={"bounded": True},
        first_seen_at=now - timedelta(days=200),
        last_seen_at=now,
        last_evaluation_id=evaluation.id,
        lifecycle_version=1,
        **(
            {
                "suppressed_at": now - timedelta(days=1),
                "suppression_reason": "Accepted temporarily",
                "suppressed_by_user_id": user.id,
            }
            if status == FindingStatus.SUPPRESSED
            else {}
        ),
    )
    db.add(finding)
    db.flush()
    return finding, asset


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}"}


def test_assessment_is_deterministic_and_historical(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, asset = _finding(db, organization, account, user)
    context = AssetRiskContext(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_id=asset.id,
        criticality=RiskCriticality.CRITICAL,
        environment=RiskEnvironment.PRODUCTION,
        business_impact=BusinessImpact.CRITICAL,
        data_sensitivity=DataSensitivity.RESTRICTED,
        source="manual",
        updated_by_user_id=user.id,
    )
    db.add(context)
    db.commit()
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    first = RiskService(db).assess(
        organization.id, user, aws_account_id=account.id, evaluation_time=evaluated
    )
    snapshot = db.scalar(
        select(FindingRiskSnapshot).where(FindingRiskSnapshot.assessment_id == first.id)
    )
    assert snapshot is not None
    assert snapshot.risk_score == 95
    assert snapshot.unknown_inputs_json == ["required_privilege"]
    original_score = snapshot.risk_score
    finding.status = FindingStatus.RESOLVED
    finding.resolved_at = evaluated + timedelta(days=1)
    db.commit()
    second = RiskService(db).assess(
        organization.id,
        user,
        aws_account_id=account.id,
        evaluation_time=evaluated + timedelta(days=1),
    )
    assert second.findings_total == 0
    db.refresh(snapshot)
    assert snapshot.risk_score == original_score


def test_suppression_does_not_reduce_risk_but_control_does(db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user, status=FindingStatus.SUPPRESSED)
    db.commit()
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    before = RiskService(db).assess(
        organization.id, user, aws_account_id=account.id, evaluation_time=evaluated
    )
    before_snapshot = db.scalar(
        select(FindingRiskSnapshot).where(FindingRiskSnapshot.assessment_id == before.id)
    )
    assert before_snapshot is not None
    assert before_snapshot.compensating_adjustment == 0
    control = RiskService(db).add_compensating_control(
        organization.id,
        finding.id,
        user,
        reason="Reviewed network control",
        score_adjustment=-10,
        expires_at=evaluated + timedelta(days=30),
    )
    assert control.active
    after = RiskService(db).assess(
        organization.id,
        user,
        aws_account_id=account.id,
        evaluation_time=evaluated + timedelta(days=1),
    )
    after_snapshot = db.scalar(
        select(FindingRiskSnapshot).where(FindingRiskSnapshot.assessment_id == after.id)
    )
    assert after_snapshot is not None
    assert after_snapshot.risk_score == before_snapshot.risk_score - 10


def test_context_optimistic_version_and_audit(db: Session) -> None:
    user, organization, account = _tenant(db)
    context = RiskService(db).update_context(
        organization.id,
        user,
        aws_account_id=account.id,
        asset_id=None,
        criticality=RiskCriticality.HIGH,
        environment=RiskEnvironment.STAGING,
        business_impact=BusinessImpact.HIGH,
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        expected_version=0,
    )
    assert context.version == 1
    updated = RiskService(db).update_context(
        organization.id,
        user,
        aws_account_id=account.id,
        asset_id=None,
        criticality=RiskCriticality.CRITICAL,
        environment=RiskEnvironment.PRODUCTION,
        business_impact=BusinessImpact.CRITICAL,
        data_sensitivity=DataSensitivity.RESTRICTED,
        expected_version=1,
    )
    assert updated.version == 2
    with pytest.raises(ConflictError, match="stale"):
        RiskService(db).update_context(
            organization.id,
            user,
            aws_account_id=account.id,
            asset_id=None,
            criticality=RiskCriticality.LOW,
            environment=RiskEnvironment.SANDBOX,
            business_impact=BusinessImpact.LOW,
            data_sensitivity=DataSensitivity.PUBLIC,
            expected_version=1,
        )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "risk.context.changed")
        )
        == 2
    )


def test_http_rbac_summary_assessment_and_cross_tenant(client: TestClient, db: Session) -> None:
    owner, organization, account = _tenant(db)
    _finding(db, organization, account, owner)
    viewer, _viewer_org, _viewer_account = _tenant(db, OrganizationRole.VIEWER)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()
    owner_headers = _headers(owner)
    response = client.post(
        "/api/v1/risk/assess",
        headers=owner_headers,
        json={
            "organization_id": str(organization.id),
            "aws_account_id": str(account.id),
            "evaluation_time": "2026-07-24T00:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    summary = client.get(
        f"/api/v1/risk/summary?organization_id={organization.id}",
        headers=owner_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["assessment"]["critical_count"] == 1
    assert client.get(f"/api/v1/risk/summary?organization_id={organization.id}").status_code == 401
    assert (
        client.post(
            "/api/v1/risk/assess",
            headers=_headers(viewer),
            json={"organization_id": str(_viewer_org.id)},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/risk/summary?organization_id={organization.id}",
            headers=_headers(other_owner),
        ).status_code
        == 404
    )
    random_detail = client.get(
        f"/api/v1/risk/assessments/{uuid.uuid4()}?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )
    assert random_detail.status_code == 404


def test_http_filters_validation_and_compensating_control(client: TestClient, db: Session) -> None:
    owner, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, owner)
    db.add(
        AssetRiskContext(
            organization_id=organization.id,
            aws_account_id=account.id,
            asset_id=_asset.id,
            criticality=RiskCriticality.CRITICAL,
            environment=RiskEnvironment.PRODUCTION,
            business_impact=BusinessImpact.CRITICAL,
            data_sensitivity=DataSensitivity.RESTRICTED,
            source="manual",
            updated_by_user_id=owner.id,
        )
    )
    db.commit()
    headers = _headers(owner)
    assessed = client.post(
        "/api/v1/risk/assess",
        headers=headers,
        json={
            "organization_id": str(organization.id),
            "aws_account_id": str(account.id),
            "evaluation_time": "2026-07-24T00:00:00Z",
        },
    )
    assert assessed.status_code == 201
    response = client.get(
        f"/api/v1/risk/findings?organization_id={organization.id}"
        "&priority=critical&minimum_score=80&page=1&page_size=10",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    invalid = client.get(
        f"/api/v1/risk/findings?organization_id={organization.id}"
        "&minimum_score=90&maximum_score=20",
        headers=headers,
    )
    assert invalid.status_code == 422
    control = client.post(
        f"/api/v1/risk/findings/{finding.id}/compensating-controls"
        f"?organization_id={organization.id}",
        headers=headers,
        json={
            "reason": "Reviewed compensating network control",
            "score_adjustment": -5,
            "expires_at": "2026-08-24T00:00:00Z",
        },
    )
    assert control.status_code == 201, control.text
    assert (
        db.scalar(
            select(func.count())
            .select_from(CompensatingControl)
            .where(CompensatingControl.finding_id == finding.id)
        )
        == 1
    )


def test_assessment_counts_match_snapshots(db: Session) -> None:
    user, organization, account = _tenant(db)
    _finding(db, organization, account, user, severity=FindingSeverity.HIGH)
    db.commit()
    assessment = RiskService(db).assess(
        organization.id,
        user,
        aws_account_id=account.id,
        evaluation_time=datetime(2026, 7, 24, tzinfo=UTC),
    )
    assert assessment.findings_total == 1
    assert assessment.high_count == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(FindingRiskSnapshot)
            .where(FindingRiskSnapshot.assessment_id == assessment.id)
        )
        == assessment.findings_total
    )
    assert db.scalar(select(func.count()).select_from(RiskAssessment)) == 1


@pytest.mark.parametrize(
    ("role", "assessment_status", "context_status"),
    [
        (OrganizationRole.OWNER, 201, 200),
        (OrganizationRole.ADMIN, 201, 200),
        (OrganizationRole.SECURITY_ANALYST, 201, 200),
        (OrganizationRole.CLOUD_ENGINEER, 201, 403),
        (OrganizationRole.AUDITOR, 403, 403),
        (OrganizationRole.VIEWER, 403, 403),
    ],
)
def test_http_six_role_risk_capability_matrix(
    client: TestClient,
    db: Session,
    role: OrganizationRole,
    assessment_status: int,
    context_status: int,
) -> None:
    user, organization, account = _tenant(db, role)
    db.commit()
    headers = _headers(user)
    assert (
        client.get(
            f"/api/v1/risk/policies?organization_id={organization.id}",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/risk/assess",
            headers=headers,
            json={
                "organization_id": str(organization.id),
                "aws_account_id": str(account.id),
                "evaluation_time": "2026-07-24T00:00:00Z",
            },
        ).status_code
        == assessment_status
    )
    assert (
        client.put(
            f"/api/v1/risk/context?organization_id={organization.id}",
            headers=headers,
            json={
                "aws_account_id": str(account.id),
                "criticality": "high",
                "environment": "production",
                "business_impact": "high",
                "data_sensitivity": "confidential",
                "expected_version": 0,
            },
        ).status_code
        == context_status
    )
