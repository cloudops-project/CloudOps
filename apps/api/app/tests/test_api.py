from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent, OrganizationInvitation, RefreshTokenSession
from app.models.enums import AuditResult
from app.tests.conftest import register_and_login


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_registration_duplicate_login_and_safe_response(
    client: TestClient, user_payload: dict[str, str]
) -> None:
    response = client.post("/api/v1/auth/register", json=user_payload)
    assert response.status_code == 201
    assert "password" not in response.text
    assert client.post("/api/v1/auth/register", json=user_payload).status_code == 409
    good = client.post(
        "/api/v1/auth/login",
        json={
            "email": user_payload["email"],
            "password": user_payload["password"],
        },
    )
    assert good.status_code == 200
    bad = client.post(
        "/api/v1/auth/login",
        json={
            "email": "missing@example.com",
            "password": "Not-The-Password-123!",
        },
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["message"] == "Invalid email or password."


def test_refresh_rotation_reuse_logout_and_password_change(client: TestClient, db: Session) -> None:
    headers = register_and_login(client)
    old_cookie = client.cookies.get("cloudops_refresh_token")
    assert old_cookie
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    new_cookie = client.cookies.get("cloudops_refresh_token")
    assert new_cookie and new_cookie != old_cookie
    client.cookies.set("cloudops_refresh_token", old_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401
    client.cookies.set("cloudops_refresh_token", new_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401
    headers = register_and_login(client, "second@example.com")
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "Strong-Password-123!",
            "new_password": "Changed-Password-456!",
        },
    )
    assert changed.status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert db.scalar(select(RefreshTokenSession)) is not None


def test_logout_audit_uses_refresh_session_actor(client: TestClient, db: Session) -> None:
    register_and_login(client, "logout@example.com")
    assert client.post("/api/v1/auth/logout").status_code == 204
    event = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.event_type == "auth.logged_out")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.actor_user_id is not None
    assert event.result == AuditResult.SUCCEEDED


def test_organization_tenant_invitation_and_member_lifecycle(
    client: TestClient, db: Session
) -> None:
    owner_headers = register_and_login(client)
    created = client.post(
        "/api/v1/organizations",
        headers=owner_headers,
        json={"name": "Organization A", "slug": "organization-a"},
    )
    assert created.status_code == 201, created.text
    org_id = created.json()["id"]
    assert created.json()["current_user_role"] == "owner"
    members = client.get(f"/api/v1/organizations/{org_id}/members", headers=owner_headers)
    assert len(members.json()) == 1
    owner_member_id = members.json()[0]["id"]
    assert (
        client.delete(
            f"/api/v1/organizations/{org_id}/members/{owner_member_id}", headers=owner_headers
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/members/{owner_member_id}/status",
            headers=owner_headers,
            json={"status": "suspended"},
        ).status_code
        == 409
    )

    invitation = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner_headers,
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert invitation.status_code == 201, invitation.text
    raw = invitation.json()["development_token"]
    assert raw and "token_hash" not in invitation.text
    duplicate = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner_headers,
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert duplicate.status_code == 409

    viewer_headers = register_and_login(client, "viewer@example.com")
    accepted = client.post(
        "/api/v1/invitations/accept", headers=viewer_headers, json={"token": raw}
    )
    assert accepted.status_code == 200, accepted.text
    assert (
        client.post(
            "/api/v1/invitations/accept", headers=viewer_headers, json={"token": raw}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/organizations/{org_id}", headers=viewer_headers).status_code == 200
    denied = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=viewer_headers,
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert denied.status_code == 403

    member_data = client.get(
        f"/api/v1/organizations/{org_id}/members", headers=owner_headers
    ).json()
    viewer = next(item for item in member_data if item["email"] == "viewer@example.com")
    member_id = viewer["id"]
    changed = client.patch(
        f"/api/v1/organizations/{org_id}/members/{member_id}/role",
        headers=owner_headers,
        json={"role": "auditor"},
    )
    assert changed.json()["role"] == "auditor"
    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/members/{member_id}/status",
            headers=owner_headers,
            json={"status": "suspended"},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/organizations/{org_id}", headers=viewer_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/members/{member_id}/status",
            headers=owner_headers,
            json={"status": "active"},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/organizations/{org_id}", headers=viewer_headers).status_code == 200
    assert (
        client.delete(
            f"/api/v1/organizations/{org_id}/members/{member_id}", headers=owner_headers
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/organizations/{org_id}", headers=viewer_headers).status_code == 404
    assert db.scalars(select(AuditEvent)).all()
    assert db.scalar(select(OrganizationInvitation)).token_hash != raw  # type: ignore[union-attr]


def test_invitation_expiry_and_cancellation(client: TestClient, db: Session) -> None:
    owner = register_and_login(client, "invite-owner@example.com")
    org_id = client.post(
        "/api/v1/organizations",
        headers=owner,
        json={"name": "Invitations", "slug": "invitations"},
    ).json()["id"]
    expired = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner,
        json={"email": "expired@example.com", "role": "viewer"},
    ).json()
    record = db.scalar(
        select(OrganizationInvitation).where(OrganizationInvitation.id == uuid.UUID(expired["id"]))
    )
    assert record
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    expired_user = register_and_login(client, "expired@example.com")
    assert (
        client.post(
            "/api/v1/invitations/accept",
            headers=expired_user,
            json={"token": expired["development_token"]},
        ).status_code
        == 409
    )

    cancelled = client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=owner,
        json={"email": "cancelled@example.com", "role": "viewer"},
    ).json()
    assert (
        client.delete(
            f"/api/v1/organizations/{org_id}/invitations/{cancelled['id']}",
            headers=owner,
        ).status_code
        == 204
    )
    cancelled_user = register_and_login(client, "cancelled@example.com")
    assert (
        client.post(
            "/api/v1/invitations/accept",
            headers=cancelled_user,
            json={"token": cancelled["development_token"]},
        ).status_code
        == 409
    )


def test_tenant_isolation_and_admin_cannot_assign_owner(client: TestClient) -> None:
    first = register_and_login(client, "first@example.com")
    org = client.post(
        "/api/v1/organizations", headers=first, json={"name": "Private", "slug": "private"}
    ).json()
    outsider = register_and_login(client, "outsider@example.com")
    assert client.get(f"/api/v1/organizations/{org['id']}", headers=outsider).status_code == 404

    invitation = client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        headers=first,
        json={"email": "admin@example.com", "role": "admin"},
    ).json()
    admin = register_and_login(client, "admin@example.com")
    client.post(
        "/api/v1/invitations/accept", headers=admin, json={"token": invitation["development_token"]}
    )
    admin_member = next(
        item
        for item in client.get(f"/api/v1/organizations/{org['id']}/members", headers=first).json()
        if item["email"] == "admin@example.com"
    )
    assert (
        client.patch(
            f"/api/v1/organizations/{org['id']}/members/{admin_member['id']}/role",
            headers=admin,
            json={"role": "owner"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "environment,token_expected", [("development", True), ("production", False)]
)
def test_invitation_token_visibility_by_environment(
    client: TestClient, environment: str, token_expected: bool
) -> None:
    configured = get_settings()
    original = configured.app_env
    configured.app_env = environment  # type: ignore[assignment]
    try:
        owner = register_and_login(client, f"{environment}-owner@example.com")
        organization_id = client.post(
            "/api/v1/organizations",
            headers=owner,
            json={"name": f"{environment.title()} Org", "slug": f"{environment}-org"},
        ).json()["id"]
        response = client.post(
            f"/api/v1/organizations/{organization_id}/invitations",
            headers=owner,
            json={"email": f"{environment}-invitee@example.com", "role": "viewer"},
        )
        assert response.status_code == 201
        assert ("development_token" in response.json()) is token_expected
    finally:
        configured.app_env = original


@pytest.mark.parametrize("operation", ["demote", "suspend", "remove"])
def test_admin_cannot_manage_owner(client: TestClient, operation: str) -> None:
    owner = register_and_login(client, f"root-{operation}@example.com")
    organization_id = client.post(
        "/api/v1/organizations",
        headers=owner,
        json={"name": f"Governance {operation}", "slug": f"governance-{operation}"},
    ).json()["id"]

    def add_member(email: str, role: str) -> tuple[dict[str, str], str]:
        invitation = client.post(
            f"/api/v1/organizations/{organization_id}/invitations",
            headers=owner,
            json={"email": email, "role": role},
        ).json()
        member_headers = register_and_login(client, email)
        client.post(
            "/api/v1/invitations/accept",
            headers=member_headers,
            json={"token": invitation["development_token"]},
        )
        member = next(
            item
            for item in client.get(
                f"/api/v1/organizations/{organization_id}/members", headers=owner
            ).json()
            if item["email"] == email
        )
        return member_headers, member["id"]

    _, target_id = add_member(f"target-{operation}@example.com", "viewer")
    promoted = client.patch(
        f"/api/v1/organizations/{organization_id}/members/{target_id}/role",
        headers=owner,
        json={"role": "owner"},
    )
    assert promoted.status_code == 200
    admin, _ = add_member(f"admin-{operation}@example.com", "admin")

    if operation == "demote":
        response = client.patch(
            f"/api/v1/organizations/{organization_id}/members/{target_id}/role",
            headers=admin,
            json={"role": "viewer"},
        )
    elif operation == "suspend":
        response = client.patch(
            f"/api/v1/organizations/{organization_id}/members/{target_id}/status",
            headers=admin,
            json={"status": "suspended"},
        )
    else:
        response = client.delete(
            f"/api/v1/organizations/{organization_id}/members/{target_id}", headers=admin
        )
    assert response.status_code == 403


def test_owner_can_manage_non_final_owner(client: TestClient) -> None:
    owner = register_and_login(client, "governing-owner@example.com")
    organization_id = client.post(
        "/api/v1/organizations",
        headers=owner,
        json={"name": "Owner Governance", "slug": "owner-governance"},
    ).json()["id"]
    invitation = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        headers=owner,
        json={"email": "second-owner@example.com", "role": "viewer"},
    ).json()
    second = register_and_login(client, "second-owner@example.com")
    accepted = client.post(
        "/api/v1/invitations/accept",
        headers=second,
        json={"token": invitation["development_token"]},
    ).json()
    assert (
        client.patch(
            f"/api/v1/organizations/{organization_id}/members/{accepted['id']}/role",
            headers=owner,
            json={"role": "owner"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/organizations/{organization_id}/members/{accepted['id']}/role",
            headers=owner,
            json={"role": "auditor"},
        ).status_code
        == 200
    )
