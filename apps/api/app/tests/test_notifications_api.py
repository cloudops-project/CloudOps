from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import NotificationEvent, User
from app.models.enums import FindingSeverity, NotificationStatus, OrganizationRole
from app.security.tokens import create_access_token
from app.services.notification_provider import MockNotificationProvider
from app.services.notifications import NotificationService
from app.tests.conftest import TestingSession
from app.tests.test_risk import _finding, _tenant
from app.worker.job_worker import JobWorker


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}"}


def _approver(db: Session, marker: str) -> User:
    user = User(
        email=f"{marker}@example.com",
        normalized_email=f"{marker}@example.com",
        password_hash="test-only-hash",
        full_name="Approver",
    )
    db.add(user)
    db.flush()
    return user


def _pending_event(db: Session) -> tuple[NotificationEvent, uuid.UUID, User]:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    return event, organization.id, user


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_list_returns_events_for_organization(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications?organization_id={organization_id}",
        headers=_headers(owner),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert body["items"][0]["id"] == str(event.id)
    assert body["items"][0]["status"] == "pending_approval"


def test_detail_returns_single_event(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications/{event.id}?organization_id={organization_id}",
        headers=_headers(owner),
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(event.id)


def test_approve_transitions_pending_to_approved(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=_headers(owner),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_at"] is not None
    assert body["approved_by_user_id"] == str(owner.id)


def test_approve_is_idempotent_returns_200_unchanged(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)
    headers = _headers(owner)
    first = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["approved_at"] == first.json()["approved_at"]


def test_deliver_success_transitions_to_delivered(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)
    headers = _headers(owner)
    client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=headers,
    )

    response = client.post(
        f"/api/v1/notifications/{event.id}/deliver?organization_id={organization_id}",
        headers=headers,
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "available"
    assert JobWorker(TestingSession, get_settings(), "notification-api-test").process_one()
    db.expire_all()
    delivered = db.get(NotificationEvent, event.id)
    assert delivered is not None
    assert delivered.status == NotificationStatus.DELIVERED
    assert delivered.delivered_at is not None
    assert delivered.attempt_count == 1


# ---------------------------------------------------------------------------
# Authorization failures
# ---------------------------------------------------------------------------


def test_list_requires_authentication(client: TestClient, db: Session) -> None:
    _event, organization_id, _owner = _pending_event(db)

    response = client.get(f"/api/v1/notifications?organization_id={organization_id}")

    assert response.status_code == 401


def test_approve_requires_notifications_approve_capability(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)
    viewer, viewer_org, _viewer_account = _tenant(db, OrganizationRole.VIEWER)
    db.commit()

    response = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=_headers(owner),
    )
    assert response.status_code == 200

    forbidden = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={viewer_org.id}",
        headers=_headers(viewer),
    )
    assert forbidden.status_code in (403, 404)


def test_deliver_requires_notifications_approve_capability(client: TestClient, db: Session) -> None:
    viewer, viewer_org, _viewer_account = _tenant(db, OrganizationRole.VIEWER)
    db.commit()

    response = client.post(
        f"/api/v1/notifications/{uuid.uuid4()}/deliver?organization_id={viewer_org.id}",
        headers=_headers(viewer),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cross-tenant access
# ---------------------------------------------------------------------------


def test_detail_cross_tenant_returns_404(client: TestClient, db: Session) -> None:
    event, _organization_id, _owner = _pending_event(db)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/notifications/{event.id}?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )

    assert response.status_code == 404


def test_approve_cross_tenant_returns_404(client: TestClient, db: Session) -> None:
    event, _organization_id, _owner = _pending_event(db)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()

    response = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )

    assert response.status_code == 404


def test_list_excludes_other_organization_events(client: TestClient, db: Session) -> None:
    _event_a, organization_a_id, owner_a = _pending_event(db)
    _event_b, _organization_b_id, _owner_b = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications?organization_id={organization_a_id}",
        headers=_headers(owner_a),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["organization_id"] == str(organization_a_id)


# ---------------------------------------------------------------------------
# Invalid lifecycle transitions
# ---------------------------------------------------------------------------


def test_approve_already_delivered_event_returns_409(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)
    headers = _headers(owner)
    client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=headers,
    )
    client.post(
        f"/api/v1/notifications/{event.id}/deliver?organization_id={organization_id}",
        headers=headers,
    )
    assert JobWorker(TestingSession, get_settings(), "notification-transition-test").process_one()

    response = client.post(
        f"/api/v1/notifications/{event.id}/approve?organization_id={organization_id}",
        headers=headers,
    )

    assert response.status_code == 409


def test_deliver_pending_approval_event_returns_409(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.post(
        f"/api/v1/notifications/{event.id}/deliver?organization_id={organization_id}",
        headers=_headers(owner),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


def test_deliver_terminal_failed_state_returns_409(client: TestClient, db: Session) -> None:
    user, organization, account = _tenant(db)
    finding, _asset = _finding(db, organization, account, user, severity=FindingSeverity.CRITICAL)
    db.commit()
    event = NotificationService(db).create_for_critical_finding(finding)
    db.commit()
    assert event is not None
    approver = _approver(db, f"approver-{uuid.uuid4().hex}")
    db.commit()
    failing_service = NotificationService(
        db, provider=MockNotificationProvider(fault_mode="always_fail")
    )
    failing_service.approve(organization.id, event.id, approver)
    db.commit()
    for _ in range(3):
        failing_service.deliver(organization.id, event.id)
        db.commit()

    response = client.post(
        f"/api/v1/notifications/{event.id}/deliver?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Response serialization
# ---------------------------------------------------------------------------


def test_response_excludes_payload_hash_field(client: TestClient, db: Session) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications/{event.id}?organization_id={organization_id}",
        headers=_headers(owner),
    )

    assert "payload_hash" not in response.json()


def test_response_serializes_status_and_channel_as_string_values(
    client: TestClient, db: Session
) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications/{event.id}?organization_id={organization_id}",
        headers=_headers(owner),
    )

    body = response.json()
    assert body["status"] == NotificationStatus.PENDING_APPROVAL.value
    assert body["channel"] == "email"


def test_response_includes_null_fields_for_pending_approval_event(
    client: TestClient, db: Session
) -> None:
    event, organization_id, owner = _pending_event(db)

    response = client.get(
        f"/api/v1/notifications/{event.id}?organization_id={organization_id}",
        headers=_headers(owner),
    )

    body = response.json()
    assert body["approved_at"] is None
    assert body["approved_by_user_id"] is None
    assert body["delivered_at"] is None
    assert body["failed_at"] is None
    assert body["failure_reason"] is None
    assert body["destination_reference"] is None
