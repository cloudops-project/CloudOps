from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import PlatformJob, User
from app.models.enums import PlatformJobStatus, PlatformJobType
from app.security.rbac import Capability
from app.services.ai_safety import redact_text
from app.services.common import record_audit
from app.services.organizations import OrganizationService

MAX_PAYLOAD_BYTES = 4096
MAX_ERROR_SUMMARY = 500
SENSITIVE_PAYLOAD_KEY = re.compile(
    r"(secret|password|credential|access.?key|session.?token|authorization|cookie|webhook|body)",
    re.I,
)
ACTIVE_STATUSES = (
    PlatformJobStatus.AVAILABLE,
    PlatformJobStatus.LEASED,
    PlatformJobStatus.RUNNING,
    PlatformJobStatus.RETRY_WAIT,
)
TERMINAL_STATUSES = (
    PlatformJobStatus.SUCCEEDED,
    PlatformJobStatus.FAILED,
    PlatformJobStatus.DEAD_LETTERED,
    PlatformJobStatus.CANCELLED,
)


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def check(value: Any, depth: int = 0) -> None:
        if depth > 4:
            raise ValueError("Job payload nesting is too deep")
        if isinstance(value, dict):
            for key, item in value.items():
                if SENSITIVE_PAYLOAD_KEY.search(str(key)):
                    raise ValueError("Job payload contains a prohibited sensitive field")
                check(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 50:
                raise ValueError("Job payload list is too large")
            for item in value:
                check(item, depth + 1)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Job payload values must be JSON scalars")

    check(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("Job payload exceeds the 4096-byte limit")
    return payload


class PlatformJobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        organization_id: uuid.UUID,
        job_type: PlatformJobType,
        reference_id: uuid.UUID,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        available_at: datetime | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        correlation_id: uuid.UUID | None = None,
        parent_job_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> tuple[PlatformJob, bool]:
        now = utc_now()
        candidate = PlatformJob(
            organization_id=organization_id,
            job_type=job_type,
            reference_id=reference_id,
            payload_json=_validated_payload(payload or {}),
            idempotency_key=idempotency_key[:160],
            priority=priority,
            max_attempts=max_attempts,
            scheduled_at=now,
            available_at=available_at or now,
            correlation_id=correlation_id or uuid.uuid4(),
            parent_job_id=parent_job_id,
        )
        try:
            with self.db.begin_nested():
                self.db.add(candidate)
                self.db.flush()
        except IntegrityError:
            existing = self.db.scalar(
                select(PlatformJob).where(
                    PlatformJob.organization_id == organization_id,
                    PlatformJob.job_type == job_type,
                    PlatformJob.idempotency_key == idempotency_key[:160],
                )
            )
            if existing is None:
                existing = self.db.scalar(
                    select(PlatformJob).where(
                        PlatformJob.organization_id == organization_id,
                        PlatformJob.job_type == job_type,
                        PlatformJob.reference_id == reference_id,
                        PlatformJob.status.in_(ACTIVE_STATUSES),
                    )
                )
            if existing is None:
                raise ConflictError(
                    "job_already_active",
                    "An active job already exists for this resource.",
                ) from None
            return existing, False
        record_audit(
            self.db,
            "platform.job.enqueued",
            "platform_job",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            resource_id=candidate.id,
            metadata={"job_type": job_type.value, "reference_id": str(reference_id)},
        )
        return candidate, True

    def acquire(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> PlatformJob | None:
        acquired_at = now or utc_now()
        statement = (
            select(PlatformJob)
            .where(
                or_(
                    (
                        PlatformJob.status.in_(
                            [PlatformJobStatus.AVAILABLE, PlatformJobStatus.RETRY_WAIT]
                        )
                        & (PlatformJob.available_at <= acquired_at)
                    ),
                    (
                        PlatformJob.status.in_(
                            [PlatformJobStatus.LEASED, PlatformJobStatus.RUNNING]
                        )
                        & (PlatformJob.lease_expires_at <= acquired_at)
                    ),
                )
            )
            .order_by(
                PlatformJob.priority.desc(),
                PlatformJob.available_at,
                PlatformJob.created_at,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = self.db.scalar(statement)
        if job is None:
            return None
        job.status = PlatformJobStatus.LEASED
        job.worker_id = worker_id[:128]
        job.lease_token = uuid.uuid4()
        job.lease_generation += 1
        job.leased_at = acquired_at
        job.lease_expires_at = acquired_at + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.started_at = None
        self.db.commit()
        return job

    def start(self, job_id: uuid.UUID, lease_token: uuid.UUID) -> PlatformJob:
        job = self._leased(job_id, lease_token, PlatformJobStatus.LEASED)
        job.status = PlatformJobStatus.RUNNING
        job.started_at = utc_now()
        self.db.commit()
        return job

    def heartbeat(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        *,
        lease_seconds: int = 60,
    ) -> PlatformJob:
        job = self._leased(job_id, lease_token, PlatformJobStatus.RUNNING)
        job.lease_expires_at = utc_now() + timedelta(seconds=lease_seconds)
        self.db.commit()
        return job

    def succeed(
        self, job_id: uuid.UUID, lease_token: uuid.UUID, result_reference: str | None = None
    ) -> PlatformJob:
        job = self._leased(job_id, lease_token, PlatformJobStatus.RUNNING)
        job.status = PlatformJobStatus.SUCCEEDED
        job.completed_at = utc_now()
        job.result_reference = result_reference[:255] if result_reference else None
        self._clear_lease(job)
        self.db.commit()
        return job

    def fail(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        *,
        error_code: str,
        error_summary: str,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ) -> PlatformJob:
        job = self._leased(job_id, lease_token, PlatformJobStatus.RUNNING)
        now = utc_now()
        job.last_error_code = re.sub(r"[^a-z0-9_.-]", "_", error_code.casefold())[:100]
        job.last_error_summary = redact_text(error_summary)[:MAX_ERROR_SUMMARY]
        if retryable and job.attempt_count < job.max_attempts:
            delay = retry_after_seconds or min(900, 2 ** min(job.attempt_count, 9))
            job.status = PlatformJobStatus.RETRY_WAIT
            job.available_at = now + timedelta(seconds=max(1, delay))
        elif retryable:
            job.status = PlatformJobStatus.DEAD_LETTERED
            job.dead_lettered_at = now
            job.failed_at = now
        else:
            job.status = PlatformJobStatus.FAILED
            job.failed_at = now
        self._clear_lease(job)
        self.db.commit()
        return job

    def get_scoped(
        self, organization_id: uuid.UUID, job_id: uuid.UUID
    ) -> PlatformJob:
        job = self.db.scalar(
            select(PlatformJob).where(
                PlatformJob.id == job_id,
                PlatformJob.organization_id == organization_id,
            )
        )
        if job is None:
            raise NotFoundError("platform_job_not_found", "Job was not found.")
        return job

    def cancel(
        self, organization_id: uuid.UUID, job_id: uuid.UUID, actor: User
    ) -> PlatformJob:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JOBS_MANAGE
        )
        job = self.get_scoped(organization_id, job_id)
        if job.status in TERMINAL_STATUSES:
            raise ConflictError("job_terminal", "A terminal job cannot be cancelled.")
        job.status = PlatformJobStatus.CANCELLED
        job.completed_at = utc_now()
        self._clear_lease(job)
        record_audit(
            self.db,
            "platform.job.cancelled",
            "platform_job",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
        )
        self.db.commit()
        return job

    def requeue(
        self, organization_id: uuid.UUID, job_id: uuid.UUID, actor: User
    ) -> PlatformJob:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JOBS_MANAGE
        )
        job = self.get_scoped(organization_id, job_id)
        if job.status not in {
            PlatformJobStatus.FAILED,
            PlatformJobStatus.DEAD_LETTERED,
            PlatformJobStatus.CANCELLED,
        }:
            raise ConflictError("job_not_requeueable", "This job cannot be requeued.")
        job.status = PlatformJobStatus.AVAILABLE
        job.available_at = utc_now()
        job.attempt_count = 0
        job.failed_at = None
        job.dead_lettered_at = None
        job.completed_at = None
        job.last_error_code = None
        job.last_error_summary = None
        self._clear_lease(job)
        record_audit(
            self.db,
            "platform.job.requeued",
            "platform_job",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
        )
        self.db.commit()
        return job

    def counts(self, organization_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(PlatformJob.status, func.count(PlatformJob.id))
            .where(PlatformJob.organization_id == organization_id)
            .group_by(PlatformJob.status)
        ).all()
        return {status.value: int(count) for status, count in rows}

    def global_counts(self) -> dict[str, int]:
        """Low-cardinality operational queue totals with no tenant dimension."""
        rows = self.db.execute(
            select(PlatformJob.status, func.count(PlatformJob.id)).group_by(
                PlatformJob.status
            )
        ).all()
        return {status.value: int(count) for status, count in rows}

    def _leased(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        expected_status: PlatformJobStatus,
    ) -> PlatformJob:
        job = self.db.scalar(
            select(PlatformJob)
            .where(
                PlatformJob.id == job_id,
                PlatformJob.lease_token == lease_token,
                PlatformJob.status == expected_status,
            )
            .with_for_update()
        )
        if job is None:
            raise ConflictError(
                "stale_job_lease", "The job lease is stale or no longer owned by this worker."
            )
        return job

    @staticmethod
    def _clear_lease(job: PlatformJob) -> None:
        job.worker_id = None
        job.lease_token = None
        job.lease_expires_at = None
