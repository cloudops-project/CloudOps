from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.exceptions.errors import ConflictError
from app.models import AuditEvent, PlatformJob
from app.models.enums import PlatformJobStatus, PlatformJobType
from app.security.tokens import create_access_token
from app.services.platform_jobs import PlatformJobService
from app.tests.conftest import TestingSession
from app.tests.test_risk import _tenant
from app.worker.job_worker import JobWorker


def _enqueue(db: Session, organization_id: uuid.UUID) -> PlatformJob:
    job, created = PlatformJobService(db).enqueue(
        organization_id=organization_id,
        job_type=PlatformJobType.DISCOVERY,
        reference_id=uuid.uuid4(),
        idempotency_key=f"phase3-{uuid.uuid4()}",
        payload={"account_id": str(uuid.uuid4()), "actor_user_id": str(uuid.uuid4())},
    )
    db.commit()
    assert created is True
    return job


def test_enqueue_is_idempotent_and_payload_rejects_sensitive_fields(db: Session) -> None:
    _user, organization, _account = _tenant(db)
    reference_id = uuid.uuid4()
    service = PlatformJobService(db)
    first, created = service.enqueue(
        organization_id=organization.id,
        job_type=PlatformJobType.DISCOVERY,
        reference_id=reference_id,
        idempotency_key="same-occurrence",
        payload={"account_id": str(reference_id)},
    )
    second, duplicate_created = service.enqueue(
        organization_id=organization.id,
        job_type=PlatformJobType.DISCOVERY,
        reference_id=reference_id,
        idempotency_key="same-occurrence",
        payload={"account_id": str(reference_id)},
    )
    assert created is True
    assert duplicate_created is False
    assert second.id == first.id
    with pytest.raises(ValueError, match="sensitive"):
        service.enqueue(
            organization_id=organization.id,
            job_type=PlatformJobType.DISCOVERY,
            reference_id=uuid.uuid4(),
            idempotency_key="secret-payload",
            payload={"session_token": "phase3-sentinel"},
        )
    assert "phase3-sentinel" not in str(db.scalars(select(AuditEvent.metadata_json)).all())


def test_lease_expiry_reacquisition_rejects_stale_completion(db: Session) -> None:
    _user, organization, _account = _tenant(db)
    job = _enqueue(db, organization.id)
    service = PlatformJobService(db)
    first = service.acquire("worker-a", lease_seconds=30)
    assert first is not None and first.id == job.id and first.lease_token is not None
    first_token = first.lease_token
    service.start(job.id, first_token)

    second = service.acquire(
        "worker-b",
        lease_seconds=30,
        now=utc_now() + timedelta(seconds=31),
    )
    assert second is not None and second.lease_token is not None
    assert second.lease_token != first_token
    assert second.lease_generation == 2
    with pytest.raises(ConflictError, match="stale"):
        service.succeed(job.id, first_token)
    service.start(job.id, second.lease_token)
    completed = service.succeed(job.id, second.lease_token, "result-id")
    assert completed.status == PlatformJobStatus.SUCCEEDED


def test_retry_backoff_and_dead_letter_after_exhaustion(db: Session) -> None:
    _user, organization, _account = _tenant(db)
    job, _created = PlatformJobService(db).enqueue(
        organization_id=organization.id,
        job_type=PlatformJobType.NOTIFICATION_DELIVERY,
        reference_id=uuid.uuid4(),
        idempotency_key="retry-test",
        max_attempts=2,
    )
    db.commit()
    service = PlatformJobService(db)
    first = service.acquire("worker-a")
    assert first is not None and first.lease_token is not None
    service.start(job.id, first.lease_token)
    retry = service.fail(
        job.id,
        first.lease_token,
        error_code="provider_429",
        error_summary="password=phase3-sentinel",
        retryable=True,
        retry_after_seconds=5,
    )
    assert retry.status == PlatformJobStatus.RETRY_WAIT
    assert "phase3-sentinel" not in (retry.last_error_summary or "")

    second = service.acquire("worker-b", now=retry.available_at + timedelta(seconds=1))
    assert second is not None and second.lease_token is not None
    service.start(job.id, second.lease_token)
    dead = service.fail(
        job.id,
        second.lease_token,
        error_code="provider_429",
        error_summary="still unavailable",
        retryable=True,
    )
    assert dead.status == PlatformJobStatus.DEAD_LETTERED
    assert dead.dead_lettered_at is not None


def test_job_monitoring_is_tenant_scoped_and_requeue_is_audited(
    client: TestClient, db: Session
) -> None:
    owner_a, organization_a, _account_a = _tenant(db)
    owner_b, organization_b, _account_b = _tenant(db)
    job = _enqueue(db, organization_a.id)
    job.status = PlatformJobStatus.DEAD_LETTERED
    job.dead_lettered_at = utc_now()
    db.commit()
    headers_b = {
        "Authorization": f"Bearer {create_access_token(owner_b.id, get_settings())}"
    }
    hidden = client.get(
        f"/api/v1/jobs/{job.id}?organization_id={organization_b.id}",
        headers=headers_b,
    )
    assert hidden.status_code == 404
    headers_a = {
        "Authorization": f"Bearer {create_access_token(owner_a.id, get_settings())}"
    }
    requeued = client.post(
        f"/api/v1/jobs/{job.id}/requeue?organization_id={organization_a.id}",
        headers=headers_a,
    )
    assert requeued.status_code == 200
    assert requeued.json()["status"] == "available"
    assert db.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "platform.job.requeued")
    ) is not None


def test_worker_renews_long_running_job_lease(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _user, organization, _account = _tenant(db)
    job = _enqueue(db, organization.id)
    settings = get_settings().model_copy(update={"job_lease_seconds": 3})
    worker = JobWorker(TestingSession, settings, "heartbeat-test")

    def slow_dispatch(_db: Session, _job: PlatformJob) -> str:
        time.sleep(1.2)
        return "synthetic-result"

    heartbeat_calls: list[uuid.UUID] = []
    original_heartbeat = PlatformJobService.heartbeat

    def record_heartbeat(
        service: PlatformJobService,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        *,
        lease_seconds: int,
    ) -> PlatformJob:
        heartbeat_calls.append(job_id)
        return original_heartbeat(
            service,
            job_id,
            lease_token,
            lease_seconds=lease_seconds,
        )

    monkeypatch.setattr(worker, "_dispatch", slow_dispatch)
    monkeypatch.setattr(PlatformJobService, "heartbeat", record_heartbeat)

    assert worker.process_one() is True
    db.expire_all()
    completed = db.get(PlatformJob, job.id)
    assert completed is not None
    assert completed.status == PlatformJobStatus.SUCCEEDED
    assert heartbeat_calls
    assert all(heartbeat_job_id == job.id for heartbeat_job_id in heartbeat_calls)
