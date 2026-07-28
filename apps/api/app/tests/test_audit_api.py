from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.models.enums import AuditResult, OrganizationRole
from app.security.tokens import create_access_token
from app.services.common import record_audit
from app.tests.test_risk import _tenant


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_list_returns_only_events_for_the_requested_organization(
    client: TestClient, db: Session
) -> None:
    user, organization, _account = _tenant(db)
    _other_owner, other_org, _other_account = _tenant(db)
    record_audit(db, "scheduler.schedule.created", "scan_schedule", organization_id=organization.id)
    record_audit(db, "scheduler.run.completed", "scan_run", organization_id=organization.id)
    record_audit(db, "scheduler.schedule.created", "scan_schedule", organization_id=other_org.id)
    db.commit()

    response = client.get(
        f"/api/v1/audit-events?organization_id={organization.id}", headers=_headers(user)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert all(item["organization_id"] == str(organization.id) for item in body["items"])


def test_filters_by_event_type_and_result(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    record_audit(
        db,
        "scheduler.run.failed",
        "scan_run",
        organization_id=organization.id,
        result=AuditResult.FAILED,
    )
    record_audit(
        db,
        "scheduler.run.completed",
        "scan_run",
        organization_id=organization.id,
        result=AuditResult.SUCCEEDED,
    )
    db.commit()

    response = client.get(
        f"/api/v1/audit-events?organization_id={organization.id}"
        "&event_type=scheduler.run.failed&result=failed",
        headers=_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "scheduler.run.failed"


def test_pagination(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    for _ in range(3):
        record_audit(
            db, "scheduler.schedule.created", "scan_schedule", organization_id=organization.id
        )
    db.commit()

    response = client.get(
        f"/api/v1/audit-events?organization_id={organization.id}&page=1&page_size=2",
        headers=_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_export_returns_csv_with_expected_rows(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    record_audit(db, "scheduler.schedule.created", "scan_schedule", organization_id=organization.id)
    record_audit(db, "scheduler.run.completed", "scan_run", organization_id=organization.id)
    db.commit()

    response = client.get(
        f"/api/v1/audit-events/export?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "id",
        "organization_id",
        "actor_user_id",
        "event_type",
        "resource_type",
        "resource_id",
        "result",
        "created_at",
    ]
    assert len(rows) == 3  # header + 2 events


def test_export_escapes_formula_injection_prefixes(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    record_audit(
        db,
        "=cmd|'/c calc'!A1",
        "+SUM(A1:A2)",
        organization_id=organization.id,
    )
    db.commit()

    response = client.get(
        f"/api/v1/audit-events/export?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    event_type, resource_type = rows[1][3], rows[1][4]
    assert event_type.startswith("'=")
    assert resource_type.startswith("'+")


# ---------------------------------------------------------------------------
# Authorization and tenancy
# ---------------------------------------------------------------------------


def test_list_requires_authentication(client: TestClient, db: Session) -> None:
    _user, organization, _account = _tenant(db)
    db.commit()

    response = client.get(f"/api/v1/audit-events?organization_id={organization.id}")

    assert response.status_code == 401


def test_list_requires_audit_read_capability(client: TestClient, db: Session) -> None:
    cloud_engineer, organization, _account = _tenant(db, OrganizationRole.CLOUD_ENGINEER)
    db.commit()

    response = client.get(
        f"/api/v1/audit-events?organization_id={organization.id}",
        headers=_headers(cloud_engineer),
    )

    assert response.status_code == 403


def test_export_requires_audit_read_capability(client: TestClient, db: Session) -> None:
    viewer, organization, _account = _tenant(db, OrganizationRole.VIEWER)
    db.commit()

    response = client.get(
        f"/api/v1/audit-events/export?organization_id={organization.id}",
        headers=_headers(viewer),
    )

    assert response.status_code == 403


def test_auditor_role_can_list_events(client: TestClient, db: Session) -> None:
    auditor, organization, _account = _tenant(db, OrganizationRole.AUDITOR)
    record_audit(db, "scheduler.schedule.created", "scan_schedule", organization_id=organization.id)
    db.commit()

    response = client.get(
        f"/api/v1/audit-events?organization_id={organization.id}", headers=_headers(auditor)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
