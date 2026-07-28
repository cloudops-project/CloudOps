from __future__ import annotations

import uuid
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Organization, ScanSchedule, User
from app.models.enums import AWSAccountStatus, OrganizationRole, ScanRunTrigger
from app.security.tokens import create_access_token
from app.services.discovery import DiscoveryOrchestrator
from app.services.scheduler import SchedulerService
from app.tests.test_risk import _tenant


class FakeDiscoveryService:
    asset_types: ClassVar[set[str]] = set()

    def discover(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


def _mock_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeDiscoveryService(),))
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, get_settings())
    return {"Authorization": f"Bearer {token}"}


def _schedule(db: Session, interval_minutes: int = 30) -> tuple[ScanSchedule, Organization, User]:
    user, organization, account = _tenant(db)
    schedule = SchedulerService(db, get_settings()).create_schedule(
        organization.id, account.id, user, name="Nightly scan", interval_minutes=interval_minutes
    )
    return schedule, organization, user


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_create_schedule_via_api(client: TestClient, db: Session) -> None:
    user, organization, account = _tenant(db)
    db.commit()

    response = client.post(
        f"/api/v1/schedules?organization_id={organization.id}",
        headers=_headers(user),
        json={
            "aws_account_id": str(account.id),
            "name": "Nightly scan",
            "interval_minutes": 60,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Nightly scan"
    assert body["enabled"] is True
    assert body["next_run_at"] is not None


def test_list_and_detail_schedules(client: TestClient, db: Session) -> None:
    schedule, organization, user = _schedule(db)
    db.commit()

    listing = client.get(
        f"/api/v1/schedules?organization_id={organization.id}", headers=_headers(user)
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = client.get(
        f"/api/v1/schedules/{schedule.id}?organization_id={organization.id}",
        headers=_headers(user),
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == str(schedule.id)


def test_enable_disable_via_api(client: TestClient, db: Session) -> None:
    schedule, organization, user = _schedule(db)
    db.commit()

    disabled = client.post(
        f"/api/v1/schedules/{schedule.id}/disable?organization_id={organization.id}",
        headers=_headers(user),
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = client.post(
        f"/api/v1/schedules/{schedule.id}/enable?organization_id={organization.id}",
        headers=_headers(user),
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_delete_via_api(client: TestClient, db: Session) -> None:
    schedule, organization, user = _schedule(db)
    db.commit()
    schedule_id = schedule.id

    response = client.delete(
        f"/api/v1/schedules/{schedule_id}?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 204

    db.expire_all()
    assert db.get(ScanSchedule, schedule_id) is None


def test_run_now_via_api(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, organization, account = _tenant(db)
    account.connection_status = AWSAccountStatus.CONNECTED
    account.status = AWSAccountStatus.CONNECTED
    db.commit()
    schedule = SchedulerService(db, get_settings()).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )
    _mock_discovery(monkeypatch)

    response = client.post(
        f"/api/v1/schedules/{schedule.id}/run?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["trigger"] == "manual"


def test_list_and_detail_scan_runs(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, organization, account = _tenant(db)
    account.connection_status = AWSAccountStatus.CONNECTED
    account.status = AWSAccountStatus.CONNECTED
    db.commit()
    schedule = SchedulerService(db, get_settings()).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )
    _mock_discovery(monkeypatch)
    run = SchedulerService(db, get_settings()).run_schedule(
        organization.id, schedule.id, user, trigger=ScanRunTrigger.MANUAL
    )

    listing = client.get(
        f"/api/v1/scan-runs?organization_id={organization.id}", headers=_headers(user)
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = client.get(
        f"/api/v1/scan-runs/{run.id}?organization_id={organization.id}",
        headers=_headers(user),
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == str(run.id)


# ---------------------------------------------------------------------------
# Authorization and tenancy
# ---------------------------------------------------------------------------


def test_list_requires_authentication(client: TestClient, db: Session) -> None:
    _schedule_row, organization, _user = _schedule(db)
    db.commit()

    response = client.get(f"/api/v1/schedules?organization_id={organization.id}")

    assert response.status_code == 401


def test_create_requires_schedule_manage_capability(client: TestClient, db: Session) -> None:
    viewer, organization, account = _tenant(db, OrganizationRole.VIEWER)
    db.commit()

    response = client.post(
        f"/api/v1/schedules?organization_id={organization.id}",
        headers=_headers(viewer),
        json={"aws_account_id": str(account.id), "name": "Scan", "interval_minutes": 30},
    )

    assert response.status_code == 403


def test_detail_cross_tenant_returns_404(client: TestClient, db: Session) -> None:
    schedule, _organization, _user = _schedule(db)
    other_owner, other_org, _other_account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/schedules/{schedule.id}?organization_id={other_org.id}",
        headers=_headers(other_owner),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_interval_below_minimum_returns_422(client: TestClient, db: Session) -> None:
    user, organization, account = _tenant(db)
    db.commit()

    response = client.post(
        f"/api/v1/schedules?organization_id={organization.id}",
        headers=_headers(user),
        json={"aws_account_id": str(account.id), "name": "Scan", "interval_minutes": 5},
    )

    assert response.status_code == 422


def test_get_unknown_schedule_returns_404(client: TestClient, db: Session) -> None:
    user, organization, _account = _tenant(db)
    db.commit()

    response = client.get(
        f"/api/v1/schedules/{uuid.uuid4()}?organization_id={organization.id}",
        headers=_headers(user),
    )

    assert response.status_code == 404
