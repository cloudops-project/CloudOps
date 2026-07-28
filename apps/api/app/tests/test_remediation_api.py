from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.models import Finding, Organization, RemediationRequest, User
from app.models.enums import FindingStatus, OrganizationRole
from app.security.tokens import create_access_token
from app.services.remediation import RemediationService
from app.tests.conftest import TestingSession
from app.tests.test_risk import _finding, _tenant
from app.worker.job_worker import JobWorker


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}"}


def _proposed(
    db: Session,
) -> tuple[RemediationRequest, Organization, User, Finding]:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()
    request = RemediationService(db).propose_for_finding(organization.id, finding.id, user)
    db.commit()
    return request, organization, user, finding


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_propose_via_api_creates_pending_approval_request(client: TestClient, db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    db.commit()

    response = client.post(
        f"/api/v1/findings/{finding.id}/remediations?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["finding_id"] == str(finding.id)
    assert len(body["remediation_steps_json"]) >= 1


def test_list_returns_requests_for_organization(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)

    response = client.get(
        f"/api/v1/remediations?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(request.id)


def test_detail_returns_single_request(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)

    response = client.get(
        f"/api/v1/remediations/{request.id}?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(request.id)


def test_approve_then_execute_via_api(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)
    headers = _headers(user)

    approved = client.post(
        f"/api/v1/remediations/{request.id}/approve?organization_id={organization.id}",
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = client.post(
        f"/api/v1/remediations/{request.id}/execute?organization_id={organization.id}",
        headers=headers,
    )
    assert executed.status_code == 202, executed.text
    body = executed.json()
    assert body["status"] == "available"
    assert body["job_type"] == "remediation_simulation"
    assert body["reference_id"] == str(request.id)
    assert JobWorker(TestingSession, get_settings(), "remediation-api-test").process_one()
    db.expire_all()
    completed = db.get(RemediationRequest, request.id)
    assert completed is not None
    assert completed.status.value == "succeeded"
    assert completed.execution_lease_id is not None
    assert completed.dry_run is True


def test_reject_via_api_requires_reason(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)

    missing_reason = client.post(
        f"/api/v1/remediations/{request.id}/reject?organization_id={organization.id}",
        headers=_headers(user),
        json={},
    )
    assert missing_reason.status_code == 422

    rejected = client.post(
        f"/api/v1/remediations/{request.id}/reject?organization_id={organization.id}",
        headers=_headers(user),
        json={"reason": "Not applicable to this environment"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_cancel_via_api(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)

    response = client.post(
        f"/api/v1/remediations/{request.id}/cancel?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Authorization failures
# ---------------------------------------------------------------------------


def test_list_requires_authentication(client: TestClient, db: Session) -> None:
    _request, organization, _user, _finding_row = _proposed(db)

    response = client.get(f"/api/v1/remediations?organization_id={organization.id}")

    assert response.status_code == 401


def test_propose_requires_remediation_request_capability(client: TestClient, db: Session) -> None:
    viewer, viewer_org, viewer_account = _tenant(db, OrganizationRole.VIEWER)
    finding, _asset = _finding(db, viewer_org, viewer_account, viewer)
    db.commit()

    response = client.post(
        f"/api/v1/findings/{finding.id}/remediations?organization_id={viewer_org.id}",
        headers=_headers(viewer),
    )

    assert response.status_code == 403


def test_approve_requires_remediation_approve_capability(client: TestClient, db: Session) -> None:
    cloud_engineer, org, account = _tenant(db, OrganizationRole.CLOUD_ENGINEER)
    finding, _asset = _finding(db, org, account, cloud_engineer)
    db.commit()
    request = RemediationService(db).propose_for_finding(org.id, finding.id, cloud_engineer)
    db.commit()

    response = client.post(
        f"/api/v1/remediations/{request.id}/approve?organization_id={org.id}",
        headers=_headers(cloud_engineer),
    )

    assert response.status_code == 403


def test_execute_requires_remediation_execute_capability(client: TestClient, db: Session) -> None:
    cloud_engineer, org, account = _tenant(db, OrganizationRole.CLOUD_ENGINEER)
    finding, _asset = _finding(db, org, account, cloud_engineer)
    db.commit()
    service = RemediationService(db)
    request = service.propose_for_finding(org.id, finding.id, cloud_engineer)
    db.commit()

    response = client.post(
        f"/api/v1/remediations/{request.id}/execute?organization_id={org.id}",
        headers=_headers(cloud_engineer),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cross-tenant access
# ---------------------------------------------------------------------------


def test_detail_cross_tenant_returns_404(client: TestClient, db: Session) -> None:
    request, _organization, _user, _finding_row = _proposed(db)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/remediations/{request.id}?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )

    assert response.status_code == 404


def test_propose_cross_tenant_finding_returns_404(client: TestClient, db: Session) -> None:
    user_a, org_a, account_a = _tenant(db)
    finding_a, _asset = _finding(db, org_a, account_a, user_a)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()

    response = client.post(
        f"/api/v1/findings/{finding_a.id}/remediations?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Invalid transitions and malformed input
# ---------------------------------------------------------------------------


def test_execute_without_approval_returns_409(client: TestClient, db: Session) -> None:
    request, organization, user, _finding_row = _proposed(db)

    response = client.post(
        f"/api/v1/remediations/{request.id}/execute?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 409


def test_propose_for_resolved_finding_returns_409(client: TestClient, db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user)
    finding.status = FindingStatus.RESOLVED
    finding.resolved_at = utc_now()
    db.flush()
    db.commit()

    response = client.post(
        f"/api/v1/findings/{finding.id}/remediations?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 409


def test_malformed_uuid_returns_422(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/remediations/not-a-uuid?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 422


def test_get_unknown_remediation_returns_404(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/remediations/{uuid.uuid4()}?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 404
