from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import utc_now
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import AuditEvent, OrganizationMembership, PlatformJob, User
from app.models.enums import (
    MembershipStatus,
    OrganizationRole,
    PlatformJobStatus,
    PlatformJobType,
)
from app.services.platform_jobs import PlatformJobService
from app.tests.test_risk import _tenant

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test"
    or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError(
        "Phase 3 PostgreSQL tests require a disposable CloudOps test database."
    )

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Phase 3 queue tests",
)


@pytest.fixture(scope="module")
def pg_engine() -> Generator[Engine, None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'platform_jobs'"
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_sessions(pg_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


def _authorized_actor(
    db: Session,
    organization_id: uuid.UUID,
    *,
    role: OrganizationRole = OrganizationRole.OWNER,
) -> User:
    marker = uuid.uuid4().hex
    actor = User(
        email=f"platform-job-actor-{marker}@example.com",
        normalized_email=f"platform-job-actor-{marker}@example.com",
        password_hash="test-only-hash",
        full_name="Platform Job Actor",
    )
    db.add(actor)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization_id,
            user_id=actor.id,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.flush()
    return actor


def test_two_workers_acquire_one_job_once(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        # This module uses a shared disposable PostgreSQL database. Quarantine
        # active rows left by earlier test runs so both workers contend only
        # for the job created by this test.
        db.execute(
            update(PlatformJob)
            .where(
                PlatformJob.status.in_(
                    [
                        PlatformJobStatus.AVAILABLE,
                        PlatformJobStatus.RETRY_WAIT,
                        PlatformJobStatus.LEASED,
                        PlatformJobStatus.RUNNING,
                    ]
                )
            )
            .values(
                status=PlatformJobStatus.CANCELLED,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                completed_at=utc_now(),
            )
        )

        _user, organization, _account = _tenant(db)
        job, _ = PlatformJobService(db).enqueue(
            organization_id=organization.id,
            job_type=PlatformJobType.DISCOVERY,
            reference_id=uuid.uuid4(),
            idempotency_key=f"worker-race-{uuid.uuid4()}",
        )
        db.commit()
        job_id = job.id

    barrier = Barrier(2)

    def acquire(worker_id: str) -> uuid.UUID | None:
        with pg_sessions() as db:
            barrier.wait()
            acquired = PlatformJobService(db).acquire(worker_id)
            return acquired.id if acquired is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(acquire, ("worker-a", "worker-b")))

    assert results.count(job_id) == 1
    assert results.count(None) == 1


def test_concurrent_idempotent_enqueue_creates_one_row(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        _user, organization, _account = _tenant(db)
        db.commit()
        organization_id = organization.id

    key = f"concurrent-idempotency-{uuid.uuid4()}"
    reference_id = uuid.uuid4()
    barrier = Barrier(2)

    def enqueue() -> tuple[uuid.UUID, bool]:
        with pg_sessions() as db:
            barrier.wait()
            job, created = PlatformJobService(db).enqueue(
                organization_id=organization_id,
                job_type=PlatformJobType.EVALUATION,
                reference_id=reference_id,
                idempotency_key=key,
            )
            db.commit()
            return job.id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: enqueue(), range(2)))

    assert len({job_id for job_id, _created in results}) == 1
    assert sorted(created for _job_id, created in results) == [False, True]

    with pg_sessions() as db:
        assert (
            db.scalar(
                select(func.count(PlatformJob.id)).where(
                    PlatformJob.organization_id == organization_id,
                    PlatformJob.job_type == PlatformJobType.EVALUATION,
                    PlatformJob.idempotency_key == key,
                )
            )
            == 1
        )


def test_cancelled_job_rejects_all_stale_worker_transitions(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        _owner, organization, _account = _tenant(db)
        canceller = _authorized_actor(db, organization.id)

        foreign_owner, foreign_organization, _foreign_account = _tenant(db)

        job, _ = PlatformJobService(db).enqueue(
            organization_id=organization.id,
            job_type=PlatformJobType.RISK_RECALCULATION,
            reference_id=uuid.uuid4(),
            idempotency_key=f"cancel-race-{uuid.uuid4()}",
            priority=100,
        )
        db.commit()

        service = PlatformJobService(db)
        acquired = service.acquire("worker-cancel")
        assert acquired is not None
        assert acquired.id == job.id
        assert acquired.lease_token is not None

        token = acquired.lease_token
        started = service.start(job.id, token)
        assert started.status == PlatformJobStatus.RUNNING

        cancelled = service.cancel(
            organization.id,
            job.id,
            canceller,
        )
        assert cancelled.status == PlatformJobStatus.CANCELLED
        assert cancelled.worker_id is None
        assert cancelled.lease_token is None
        assert cancelled.lease_expires_at is None
        assert cancelled.result_reference is None

        with pytest.raises(ConflictError, match="stale"):
            service.succeed(
                job.id,
                token,
                result_reference="must-not-be-persisted",
            )

        with pytest.raises(ConflictError, match="stale"):
            service.fail(
                job.id,
                token,
                error_code="synthetic_retryable_failure",
                error_summary="Must not replace cancellation",
                retryable=True,
            )

        with pytest.raises(ConflictError, match="stale"):
            service.fail(
                job.id,
                token,
                error_code="synthetic_permanent_failure",
                error_summary="Must not replace cancellation",
                retryable=False,
            )

        with pytest.raises(ConflictError, match="stale"):
            service.heartbeat(job.id, token)

        # A repeated cancellation cannot create another side effect.
        with pytest.raises(ConflictError, match="terminal"):
            service.cancel(
                organization.id,
                job.id,
                canceller,
            )

        # Tenant-scoped retrieval and management conceal the foreign job.
        with pytest.raises(NotFoundError):
            service.get_scoped(
                foreign_organization.id,
                job.id,
            )

        with pytest.raises(NotFoundError):
            service.cancel(
                foreign_organization.id,
                job.id,
                foreign_owner,
            )

        # Worker transitions require the active lease token. A caller from
        # another tenant has no valid token and cannot mutate the job.
        foreign_token = uuid.uuid4()

        with pytest.raises(ConflictError, match="stale"):
            service.heartbeat(job.id, foreign_token)

        with pytest.raises(ConflictError, match="stale"):
            service.succeed(
                job.id,
                foreign_token,
                result_reference="foreign-result",
            )

        with pytest.raises(ConflictError, match="stale"):
            service.fail(
                job.id,
                foreign_token,
                error_code="foreign_failure",
                error_summary="Foreign tenant must not mutate this job",
                retryable=False,
            )

        db.expire_all()
        persisted = db.get(PlatformJob, job.id)
        assert persisted is not None
        assert persisted.status == PlatformJobStatus.CANCELLED
        assert persisted.worker_id is None
        assert persisted.lease_token is None
        assert persisted.lease_expires_at is None
        assert persisted.result_reference is None
        assert persisted.last_error_code is None
        assert persisted.last_error_summary is None

        cancellation_audit_count = db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == "platform.job.cancelled",
                AuditEvent.resource_type == "platform_job",
                AuditEvent.resource_id == job.id,
                AuditEvent.organization_id == organization.id,
                AuditEvent.actor_user_id == canceller.id,
            )
        )
        assert cancellation_audit_count == 1


def test_heartbeat_extends_lease_and_rejects_stale_token(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        _owner, organization, _account = _tenant(db)
        job, _ = PlatformJobService(db).enqueue(
            organization_id=organization.id,
            job_type=PlatformJobType.DISCOVERY,
            reference_id=uuid.uuid4(),
            idempotency_key=f"heartbeat-{uuid.uuid4()}",
            priority=100,
        )
        db.commit()

        service = PlatformJobService(db)
        acquired = service.acquire(
            "worker-heartbeat",
            lease_seconds=30,
        )
        assert acquired is not None
        assert acquired.id == job.id
        assert acquired.lease_token is not None
        assert acquired.lease_expires_at is not None

        token = acquired.lease_token
        original_expiry = acquired.lease_expires_at

        started = service.start(job.id, token)
        assert started.status == PlatformJobStatus.RUNNING

        stale_token = uuid.uuid4()

        with pytest.raises(ConflictError, match="stale"):
            service.heartbeat(
                job.id,
                stale_token,
                lease_seconds=120,
            )

        with pytest.raises(ConflictError, match="stale"):
            service.succeed(job.id, stale_token)

        with pytest.raises(ConflictError, match="stale"):
            service.fail(
                job.id,
                stale_token,
                error_code="foreign_failure",
                error_summary="Foreign lease token",
                retryable=False,
            )

        renewed = service.heartbeat(
            job.id,
            token,
            lease_seconds=120,
        )
        assert renewed.status == PlatformJobStatus.RUNNING
        assert renewed.lease_token == token
        assert renewed.worker_id == "worker-heartbeat"
        assert renewed.lease_expires_at is not None
        assert renewed.lease_expires_at > original_expiry


@pytest.mark.parametrize(
    ("terminal_status", "retryable"),
    [
        (PlatformJobStatus.SUCCEEDED, None),
        (PlatformJobStatus.FAILED, False),
        (PlatformJobStatus.DEAD_LETTERED, True),
    ],
)
def test_terminal_job_rejects_heartbeat(
    pg_sessions: sessionmaker[Session],
    terminal_status: PlatformJobStatus,
    retryable: bool | None,
) -> None:
    with pg_sessions() as db:
        _owner, organization, _account = _tenant(db)
        job, _ = PlatformJobService(db).enqueue(
            organization_id=organization.id,
            job_type=PlatformJobType.EVALUATION,
            reference_id=uuid.uuid4(),
            idempotency_key=f"terminal-heartbeat-{terminal_status.value}-{uuid.uuid4()}",
            priority=100,
        )

        if terminal_status == PlatformJobStatus.DEAD_LETTERED:
            job.max_attempts = 1

        db.commit()

        service = PlatformJobService(db)
        acquired = service.acquire(
            f"worker-{terminal_status.value}",
            lease_seconds=30,
        )
        assert acquired is not None
        assert acquired.id == job.id
        assert acquired.lease_token is not None

        token = acquired.lease_token
        service.start(job.id, token)

        if terminal_status == PlatformJobStatus.SUCCEEDED:
            terminal = service.succeed(
                job.id,
                token,
                result_reference="synthetic-result",
            )
        else:
            assert retryable is not None
            terminal = service.fail(
                job.id,
                token,
                error_code=f"synthetic_{terminal_status.value}",
                error_summary="Synthetic terminal transition",
                retryable=retryable,
            )

        assert terminal.status == terminal_status
        assert terminal.worker_id is None
        assert terminal.lease_token is None
        assert terminal.lease_expires_at is None

        with pytest.raises(ConflictError, match="stale"):
            service.heartbeat(
                job.id,
                token,
                lease_seconds=120,
            )
