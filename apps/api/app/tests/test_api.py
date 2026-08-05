from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import AuditEvent, OrganizationInvitation, RefreshTokenSession
from app.models.enums import AuditResult
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
)
from app.tests.conftest import register_and_login


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_load_balancer_host_bypass_is_limited_to_health_paths(
    client: TestClient,
) -> None:
    target_ip_host = {"Host": "10.20.1.42:8000"}

    assert client.get("/health", headers=target_ip_host).status_code == 200
    assert client.get("/ready", headers=target_ip_host).status_code == 200
    assert client.get("/api/v1/organizations", headers=target_ip_host).status_code == 400
    assert client.get("/health", headers={"Host": "untrusted.example"}).status_code == 400


def test_readiness_reports_503_without_leaking_details_on_db_failure(
    client: TestClient,
) -> None:
    _SENTINEL_MESSAGE = "synthetic connection failure: db.internal:5432"

    class _FailingSession:
        def execute(self, *args: object, **kwargs: object) -> None:
            raise SQLAlchemyError(_SENTINEL_MESSAGE)

    def override_with_failure() -> Iterator[_FailingSession]:
        yield _FailingSession()

    previous_override = app.dependency_overrides[get_db_session]
    app.dependency_overrides[get_db_session] = override_with_failure
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides[get_db_session] = previous_override

    body = response.json()
    assert response.status_code == 503
    assert body["error"]["code"] == "dependency_unavailable"
    rendered = str(body)
    assert "synthetic connection failure" not in rendered
    assert "db.internal" not in rendered
    assert "5432" not in rendered


def test_security_headers_present_and_no_hsts_outside_production(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "permissions-policy" in response.headers
    # The test app runs with APP_ENV=testing; HSTS must never be advertised
    # over a connection that isn't guaranteed HTTPS.
    assert "strict-transport-security" not in response.headers


def test_auth_responses_are_not_cached(client: TestClient) -> None:
    headers = register_and_login(client)
    assert client.get("/api/v1/auth/me", headers=headers).headers.get("cache-control") == "no-store"


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
    cookie = good.headers["set-cookie"].casefold()
    assert "cloudops_refresh_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api/v1/auth" in cookie
    assert "max-age=" in cookie
    assert "expires=" in cookie
    assert "secure" not in cookie
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


def test_refresh_and_logout_reject_mismatched_origin(client: TestClient) -> None:
    register_and_login(client)
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    # A same-origin request (matching CORS_ALLOWED_ORIGINS) is unaffected.
    assert (
        client.post("/api/v1/auth/refresh", headers={"origin": "http://localhost:5173"}).status_code
        == 200
    )


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
    listed_invitations = client.get(
        f"/api/v1/organizations/{org_id}/invitations", headers=owner_headers
    )
    assert listed_invitations.status_code == 200
    assert all("development_token" not in item for item in listed_invitations.json())

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


def test_development_smtp_invitation_sends_mailpit_link(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, object]] = []

    class CapturingProvider:
        key = "smtp"

        def deliver(self, **kwargs: object) -> NotificationDeliveryResult:
            sent.append(dict(kwargs))
            return NotificationDeliveryResult(outcome=NotificationDeliveryOutcome.SUCCESS)

    configured = get_settings()
    original_env = configured.app_env
    original_provider = configured.notification_provider
    original_frontend = configured.frontend_url
    configured.app_env = "development"
    configured.notification_provider = "smtp"
    configured.frontend_url = "http://localhost:5173"
    monkeypatch.setattr(
        "app.services.invitations.notification_provider_from_settings",
        lambda settings: CapturingProvider(),
    )
    try:
        owner = register_and_login(client, "smtp-invite-owner@example.com")
        organization_id = client.post(
            "/api/v1/organizations",
            headers=owner,
            json={"name": "SMTP Invitations", "slug": "smtp-invitations"},
        ).json()["id"]
        response = client.post(
            f"/api/v1/organizations/{organization_id}/invitations",
            headers=owner,
            json={"email": "engineer-demo@example.com", "role": "cloud_engineer"},
        )
        assert response.status_code == 201, response.text
        raw = response.json()["development_token"]
        assert raw
        assert len(sent) == 1
        assert sent[0]["recipients"] == ["engineer-demo@example.com"]
        assert sent[0]["subject"] == "[LOCAL DEMO ONLY] CloudOps organization invitation"
        text_body = str(sent[0]["text_body"])
        assert "LOCAL DEMO ONLY — NEVER USE IN PRODUCTION." in text_body
        assert f"http://localhost:5173/invitations/accept?token={raw}" in text_body
        assert "SMTP Invitations" in text_body
        assert "cloud_engineer" in text_body
    finally:
        configured.app_env = original_env
        configured.notification_provider = original_provider
        configured.frontend_url = original_frontend


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


@pytest.mark.parametrize("operation", ["demote", "suspend", "remove"])
def test_final_active_owner_cannot_be_changed(client: TestClient, operation: str) -> None:
    owner = register_and_login(client, f"sole-owner-{operation}@example.com")
    organization = client.post(
        "/api/v1/organizations",
        headers=owner,
        json={"name": f"Sole Owner {operation}", "slug": f"sole-owner-{operation}"},
    ).json()
    organization_id = organization["id"]
    owner_member_id = next(
        item
        for item in client.get(
            f"/api/v1/organizations/{organization_id}/members", headers=owner
        ).json()
        if item["email"] == f"sole-owner-{operation}@example.com"
    )["id"]

    if operation == "demote":
        response = client.patch(
            f"/api/v1/organizations/{organization_id}/members/{owner_member_id}/role",
            headers=owner,
            json={"role": "admin"},
        )
    elif operation == "suspend":
        response = client.patch(
            f"/api/v1/organizations/{organization_id}/members/{owner_member_id}/status",
            headers=owner,
            json={"status": "suspended"},
        )
    else:
        response = client.delete(
            f"/api/v1/organizations/{organization_id}/members/{owner_member_id}",
            headers=owner,
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_owner"
