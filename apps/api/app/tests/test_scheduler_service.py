from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.exceptions.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import AWSAccount, Organization, ScanRun, ScanSchedule, User
from app.models.enums import AWSAccountStatus, OrganizationRole, ScanRunStatus, ScanRunTrigger
from app.services.discovery import DiscoveryOrchestrator
from app.services.scheduler import SchedulerService
from app.tests.conftest import TestingSession
from app.tests.test_risk import _tenant
from app.worker.job_worker import JobWorker


class FakeDiscoveryService:
    asset_types: ClassVar[set[str]] = set()

    def discover(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


def _connected_tenant(
    db: Session, role: OrganizationRole = OrganizationRole.OWNER
) -> tuple[User, Organization, AWSAccount]:
    user, organization, account = _tenant(db, role)
    account.connection_status = AWSAccountStatus.CONNECTED
    account.status = AWSAccountStatus.CONNECTED
    db.commit()
    return user, organization, account


def _mock_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DiscoveryOrchestrator, "services", (FakeDiscoveryService(),))
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())


def _service(db: Session) -> SchedulerService:
    return SchedulerService(db, get_settings())


# ---------------------------------------------------------------------------
# Schedule creation and lifecycle
# ---------------------------------------------------------------------------


def test_create_schedule_computes_next_run(db: Session) -> None:
    user, organization, account = _tenant(db)
    before = utc_now()

    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Nightly scan", interval_minutes=60
    )

    assert schedule.enabled is True
    assert schedule.next_run_at is not None
    assert schedule.next_run_at >= before + timedelta(minutes=59)
    assert schedule.created_by_user_id == user.id


def test_create_schedule_requires_capability(db: Session) -> None:
    viewer, organization, account = _tenant(db, OrganizationRole.VIEWER)

    with pytest.raises(ForbiddenError):
        _service(db).create_schedule(
            organization.id, account.id, viewer, name="Nightly scan", interval_minutes=60
        )


def test_create_schedule_is_tenant_isolated(db: Session) -> None:
    user_a, org_a, _account_a = _tenant(db)
    _user_b, _org_b, account_b = _tenant(db)

    with pytest.raises(NotFoundError):
        _service(db).create_schedule(
            org_a.id, account_b.id, user_a, name="Cross tenant", interval_minutes=60
        )


def test_set_enabled_disable_clears_next_run_and_reenable_recomputes(db: Session) -> None:
    user, organization, account = _tenant(db)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )

    disabled = _service(db).set_enabled(organization.id, schedule.id, user, enabled=False)
    assert disabled.enabled is False
    assert disabled.next_run_at is None

    reenabled = _service(db).set_enabled(organization.id, schedule.id, user, enabled=True)
    assert reenabled.enabled is True
    assert reenabled.next_run_at is not None


def test_delete_schedule_removes_it(db: Session) -> None:
    user, organization, account = _tenant(db)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )

    _service(db).delete_schedule(organization.id, schedule.id, user)

    assert db.get(ScanSchedule, schedule.id) is None


# ---------------------------------------------------------------------------
# Running a schedule
# ---------------------------------------------------------------------------


def test_run_schedule_disabled_is_rejected(db: Session) -> None:
    user, organization, account = _tenant(db)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )
    _service(db).set_enabled(organization.id, schedule.id, user, enabled=False)

    with pytest.raises(ConflictError):
        _service(db).run_schedule(organization.id, schedule.id, user, trigger=ScanRunTrigger.MANUAL)


def test_manual_run_succeeds_and_records_jobs(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, organization, account = _connected_tenant(db)
    _mock_discovery(monkeypatch)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )

    run = _service(db).run_schedule(
        organization.id, schedule.id, user, trigger=ScanRunTrigger.MANUAL
    )
    worker = JobWorker(TestingSession, get_settings(), "scheduler-service-test")
    assert worker.process_one()
    assert worker.process_one()
    assert worker.process_one()
    db.refresh(run)

    assert run.status == ScanRunStatus.COMPLETED
    assert run.discovery_job_id is not None
    assert run.evaluation_job_id is not None
    assert run.started_at is not None
    assert run.finished_at is not None
    db.refresh(schedule)
    assert schedule.last_run_at == run.finished_at
    assert schedule.next_run_at is not None and schedule.next_run_at > run.finished_at


def test_run_against_unconnected_account_fails_deterministically_and_reschedules(
    db: Session,
) -> None:
    user, organization, account = _tenant(db)  # connection_status stays PENDING
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )

    run = _service(db).run_schedule(
        organization.id, schedule.id, user, trigger=ScanRunTrigger.MANUAL
    )
    worker = JobWorker(TestingSession, get_settings(), "scheduler-failure-test")
    assert worker.process_one()
    assert worker.process_one()
    db.refresh(run)

    assert run.status == ScanRunStatus.FAILED
    assert run.error_summary is not None
    assert run.finished_at is not None
    db.refresh(schedule)
    assert schedule.next_run_at is not None


def test_overlap_protection_rejects_concurrent_run(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, organization, account = _connected_tenant(db)
    _mock_discovery(monkeypatch)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=30
    )
    db.add(
        ScanRun(
            organization_id=organization.id,
            aws_account_id=account.id,
            schedule_id=schedule.id,
            trigger=ScanRunTrigger.MANUAL,
            status=ScanRunStatus.RUNNING,
            started_at=utc_now(),
        )
    )
    db.commit()

    with pytest.raises(ConflictError):
        _service(db).run_schedule(organization.id, schedule.id, user, trigger=ScanRunTrigger.MANUAL)


# ---------------------------------------------------------------------------
# Worker orchestration
# ---------------------------------------------------------------------------


def test_run_due_schedules_runs_due_and_skips_future(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, organization, account = _connected_tenant(db)
    _mock_discovery(monkeypatch)
    due = _service(db).create_schedule(
        organization.id, account.id, user, name="Due", interval_minutes=15
    )
    due.next_run_at = utc_now() - timedelta(minutes=1)
    _user2, organization2, account2 = _connected_tenant(db)
    not_due = _service(db).create_schedule(
        organization2.id, account2.id, _user2, name="Not due", interval_minutes=60
    )
    db.commit()

    runs = _service(db).run_due_schedules()

    run_schedule_ids = {run.schedule_id for run in runs}
    assert due.id in run_schedule_ids
    assert not_due.id not in run_schedule_ids


def test_run_due_schedules_skips_disabled(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, organization, account = _connected_tenant(db)
    _mock_discovery(monkeypatch)
    schedule = _service(db).create_schedule(
        organization.id, account.id, user, name="Scan", interval_minutes=15
    )
    schedule.next_run_at = utc_now() - timedelta(minutes=1)
    schedule.enabled = False
    db.commit()

    runs = _service(db).run_due_schedules()

    assert runs == []
