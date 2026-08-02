from __future__ import annotations

import logging
import signal
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.exceptions.errors import AppError, ConflictError, NotFoundError
from app.models import PlatformJob, ScanRun, ScanSchedule, User
from app.models.enums import (
    NotificationStatus,
    PlatformJobStatus,
    PlatformJobType,
    RemediationExecutionMode,
    RemediationStatus,
    ScanRunStatus,
)
from app.security.rbac import Capability
from app.services.discovery import DiscoveryOrchestrator
from app.services.evaluations import EvaluationService
from app.services.notifications import NotificationService
from app.services.organizations import OrganizationService
from app.services.platform_jobs import PlatformJobService
from app.services.remediation import RemediationService
from app.worker.heartbeat import touch as touch_heartbeat

logger = logging.getLogger("cloudops.worker")


@dataclass(frozen=True)
class RetryableJobError(Exception):
    code: str
    summary: str
    retry_after_seconds: int | None = None


class JobWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        worker_id: str,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.worker_id = worker_id[:128]
        self.stop_event = threading.Event()

    def process_one(self) -> bool:
        with self.session_factory() as db:
            job = PlatformJobService(db).acquire(
                self.worker_id, lease_seconds=self.settings.job_lease_seconds
            )
            if job is None:
                return False
            token = job.lease_token
            assert token is not None
            PlatformJobService(db).start(job.id, token)
            logger.info(
                "platform.job.started",
                extra={
                    "job_id": str(job.id),
                    "correlation_id": str(job.correlation_id),
                    "job_type": job.job_type.value,
                    "attempt": job.attempt_count,
                    "worker_id": self.worker_id,
                },
            )
            # Establish one renewal before dispatch so short leases do not
            # depend on OS thread scheduling for their first safety margin.
            PlatformJobService(db).heartbeat(
                job.id,
                token,
                lease_seconds=self.settings.job_lease_seconds,
            )
            logger.info(
                "platform.job.heartbeat",
                extra={"job_id": str(job.id), "worker_id": self.worker_id},
            )
            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._heartbeat_lease,
                args=(job.id, token, heartbeat_stop),
                name=f"job-heartbeat-{job.id}",
                daemon=True,
            )
            heartbeat.start()
            started = time.perf_counter()
            try:
                result = self._dispatch(db, job)
            except RetryableJobError as exc:
                self._record_failure(
                    db,
                    job,
                    token,
                    error_code=exc.code,
                    error_summary=exc.summary,
                    retryable=True,
                    retry_after_seconds=exc.retry_after_seconds,
                )
            except AppError as exc:
                self._record_failure(
                    db,
                    job,
                    token,
                    error_code=exc.code,
                    error_summary=exc.message,
                    retryable=False,
                )
            except Exception:
                self._record_failure(
                    db,
                    job,
                    token,
                    error_code="worker_unexpected_error",
                    error_summary="The job failed because of an unexpected internal error.",
                    retryable=True,
                )
            else:
                try:
                    completed = PlatformJobService(db).succeed(job.id, token, result)
                    logger.info(
                        "platform.job.succeeded",
                        extra={
                            "job_id": str(job.id),
                            "correlation_id": str(job.correlation_id),
                            "job_type": job.job_type.value,
                            "attempt": job.attempt_count,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000,
                                2,
                            ),
                            "terminal_status": completed.status.value,
                        },
                    )
                except ConflictError:
                    logger.warning(
                        "platform.job.stale_completion_ignored",
                        extra={"job_id": str(job.id), "worker_id": self.worker_id},
                    )
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=2)
            return True

    def run_forever(self) -> None:
        next_metrics_at = 0.0
        while not self.stop_event.is_set():
            touch_heartbeat()
            now = time.monotonic()
            if now >= next_metrics_at:
                self._emit_queue_metrics()
                next_metrics_at = now + 60
            if not self.process_one():
                self.stop_event.wait(self.settings.job_poll_interval_seconds)
        touch_heartbeat()

    def stop(self) -> None:
        self.stop_event.set()

    def _emit_queue_metrics(self) -> None:
        try:
            with self.session_factory() as db:
                counts = PlatformJobService(db).global_counts()
            logger.info(
                "platform.queue.snapshot",
                extra={
                    "queue_available": counts.get(PlatformJobStatus.AVAILABLE.value, 0),
                    "queue_running": counts.get(PlatformJobStatus.RUNNING.value, 0),
                    "queue_retry_wait": counts.get(
                        PlatformJobStatus.RETRY_WAIT.value,
                        0,
                    ),
                    "queue_dead_lettered": counts.get(
                        PlatformJobStatus.DEAD_LETTERED.value,
                        0,
                    ),
                },
            )
        except Exception:
            logger.warning("platform.queue.metrics_failed")

    def _record_failure(
        self,
        db: Session,
        job: PlatformJob,
        lease_token: uuid.UUID,
        *,
        error_code: str,
        error_summary: str,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        try:
            terminal = PlatformJobService(db).fail(
                job.id,
                lease_token,
                error_code=error_code,
                error_summary=error_summary,
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
            )
        except ConflictError:
            logger.warning(
                "platform.job.stale_failure_ignored",
                extra={"job_id": str(job.id), "worker_id": self.worker_id},
            )
            return
        self._finish_scan_run_if_terminal(db, job, terminal)
        logger.warning(
            "platform.job.failed",
            extra={
                "job_id": str(job.id),
                "correlation_id": str(job.correlation_id),
                "job_type": job.job_type.value,
                "attempt": job.attempt_count,
                "error_code": terminal.last_error_code,
                "retryable": retryable,
                "terminal_status": terminal.status.value,
            },
        )

    def _heartbeat_lease(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        stop_event: threading.Event,
    ) -> None:
        # Renew with enough margin for scheduler and database latency. Waiting
        # until one-third of a short lease made the first heartbeat race a job
        # completing under load.
        interval = max(0.25, self.settings.job_lease_seconds / 4)
        while not stop_event.wait(interval):
            try:
                with self.session_factory() as heartbeat_db:
                    PlatformJobService(heartbeat_db).heartbeat(
                        job_id,
                        lease_token,
                        lease_seconds=self.settings.job_lease_seconds,
                    )
                logger.info(
                    "platform.job.heartbeat",
                    extra={"job_id": str(job_id), "worker_id": self.worker_id},
                )
            except ConflictError:
                return
            except Exception:
                logger.warning(
                    "platform.job.heartbeat_failed",
                    extra={"job_id": str(job_id), "worker_id": self.worker_id},
                )
                return

    def _dispatch(self, db: Session, job: PlatformJob) -> str | None:
        handlers = {
            PlatformJobType.SCHEDULED_SCAN: self._scheduled_scan,
            PlatformJobType.DISCOVERY: self._discovery,
            PlatformJobType.EVALUATION: self._evaluation,
            PlatformJobType.NOTIFICATION_DELIVERY: self._notification_delivery,
            PlatformJobType.REMEDIATION_SIMULATION: self._remediation,
        }
        handler = handlers.get(job.job_type)
        if handler is None:
            raise AppError(
                "unsupported_job_type",
                "This job type has no registered worker handler.",
                409,
            )
        return handler(db, job)

    def _scheduled_scan(self, db: Session, job: PlatformJob) -> str:
        run_id = _uuid_value(job.payload_json, "scan_run_id")
        actor_id = _uuid_value(job.payload_json, "actor_user_id")
        run = db.scalar(
            select(ScanRun)
            .where(
                ScanRun.id == run_id,
                ScanRun.organization_id == job.organization_id,
                ScanRun.status == ScanRunStatus.PENDING,
            )
            .with_for_update()
        )
        if run is None:
            raise ConflictError("scan_run_not_pending", "The scan run is not pending.")
        run.status = ScanRunStatus.RUNNING
        run.started_at = utc_now()
        child, _created = PlatformJobService(db).enqueue(
            organization_id=job.organization_id,
            job_type=PlatformJobType.DISCOVERY,
            reference_id=run.aws_account_id,
            idempotency_key=f"scan-discovery:{run.id}",
            payload={
                "account_id": str(run.aws_account_id),
                "actor_user_id": str(actor_id),
                "scan_run_id": str(run.id),
            },
            correlation_id=job.correlation_id,
            parent_job_id=job.id,
        )
        db.commit()
        return str(child.id)

    def _discovery(self, db: Session, job: PlatformJob) -> str:
        account_id = _uuid_value(job.payload_json, "account_id")
        actor = self._actor(db, job, _uuid_value(job.payload_json, "actor_user_id"))
        discovered = DiscoveryOrchestrator(db, self.settings).start(account_id, actor)
        scan_run_id = _optional_uuid(job.payload_json, "scan_run_id")
        if scan_run_id is not None:
            run = self._scan_run(db, job.organization_id, scan_run_id)
            run.discovery_job_id = discovered.id
            child, _created = PlatformJobService(db).enqueue(
                organization_id=job.organization_id,
                job_type=PlatformJobType.EVALUATION,
                reference_id=account_id,
                idempotency_key=f"scan-evaluation:{run.id}:{discovered.id}",
                payload={
                    "account_id": str(account_id),
                    "actor_user_id": str(actor.id),
                    "discovery_job_id": str(discovered.id),
                    "scan_run_id": str(run.id),
                },
                correlation_id=job.correlation_id,
                parent_job_id=job.id,
            )
            db.commit()
            return str(child.id)
        return str(discovered.id)

    def _evaluation(self, db: Session, job: PlatformJob) -> str:
        account_id = _uuid_value(job.payload_json, "account_id")
        actor = self._actor(db, job, _uuid_value(job.payload_json, "actor_user_id"))
        evaluated = EvaluationService(db).start(
            account_id,
            actor,
            discovery_job_id=_optional_uuid(job.payload_json, "discovery_job_id"),
        )
        scan_run_id = _optional_uuid(job.payload_json, "scan_run_id")
        if scan_run_id is not None:
            run = self._scan_run(db, job.organization_id, scan_run_id)
            run.evaluation_job_id = evaluated.id
            run.status = ScanRunStatus.COMPLETED
            run.finished_at = utc_now()
            if run.schedule_id is not None:
                schedule = db.scalar(
                    select(ScanSchedule).where(
                        ScanSchedule.id == run.schedule_id,
                        ScanSchedule.organization_id == job.organization_id,
                    )
                )
                if schedule is not None:
                    schedule.last_run_at = run.finished_at
            db.commit()
        return str(evaluated.id)

    def _notification_delivery(self, db: Session, job: PlatformJob) -> str:
        event_id = _uuid_value(job.payload_json, "notification_event_id")
        # NotificationService.deliver reloads tenant scope and rechecks APPROVED
        # immediately before provider I/O.
        service = NotificationService(db)
        event = service.deliver(job.organization_id, event_id)
        db.commit()
        result = service.last_result
        if (
            event.status == NotificationStatus.APPROVED
            and result is not None
            and result.retryable
        ):
            raise RetryableJobError(
                result.error_code or "notification_provider_transient",
                result.sanitized_error
                or "The notification provider reported a retryable failure.",
                result.retry_after_seconds,
            )
        if event.status != NotificationStatus.DELIVERED:
            raise ConflictError(
                "notification_delivery_terminal",
                "The notification could not be delivered.",
            )
        return str(event.id)

    def _remediation(self, db: Session, job: PlatformJob) -> str:
        request_id = _uuid_value(job.payload_json, "remediation_request_id")
        actor_id = _uuid_value(job.payload_json, "actor_user_id")
        actor = self._actor(db, job, actor_id)
        OrganizationService(db).require_capability(
            job.organization_id,
            actor.id,
            Capability.REMEDIATION_EXECUTE,
        )
        request = RemediationService(db).execute(
            job.organization_id,
            request_id,
            execution_lease_id=job.id,
        )
        db.commit()
        if request.status == RemediationStatus.APPROVED:
            raise RetryableJobError(
                "remediation_retryable",
                "The simulated remediation requested a retry.",
            )
        if request.status != RemediationStatus.SUCCEEDED:
            raise ConflictError(
                "remediation_terminal_failure",
                "The remediation did not succeed.",
            )
        if request.execution_mode == RemediationExecutionMode.LIVE_AWS:
            PlatformJobService(db).enqueue(
                organization_id=job.organization_id,
                job_type=PlatformJobType.DISCOVERY,
                reference_id=request.aws_account_id,
                idempotency_key=f"remediation-rediscovery:{request.id}",
                payload={
                    "aws_account_id": str(request.aws_account_id),
                    "actor_user_id": str(actor.id),
                },
                correlation_id=job.correlation_id,
                parent_job_id=job.id,
                actor_user_id=actor.id,
            )
        return str(request.id)

    @staticmethod
    def _actor(db: Session, job: PlatformJob, actor_id: uuid.UUID) -> User:
        actor = db.get(User, actor_id)
        if actor is None:
            raise NotFoundError("job_actor_not_found", "The accountable job actor was not found.")
        # Downstream services reauthorize the actor against the tenant-owned
        # account; the queue payload is never treated as authorization.
        return actor

    @staticmethod
    def _scan_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> ScanRun:
        run = db.scalar(
            select(ScanRun).where(
                ScanRun.id == run_id,
                ScanRun.organization_id == organization_id,
            )
        )
        if run is None:
            raise NotFoundError("scan_run_not_found", "The scan run was not found.")
        return run

    @staticmethod
    def _finish_scan_run_if_terminal(
        db: Session, source_job: PlatformJob, terminal_job: PlatformJob
    ) -> None:
        if terminal_job.status not in {
            PlatformJobStatus.FAILED,
            PlatformJobStatus.DEAD_LETTERED,
        }:
            return
        run_id = _optional_uuid(source_job.payload_json, "scan_run_id")
        if run_id is None:
            return
        run = db.scalar(
            select(ScanRun).where(
                ScanRun.id == run_id,
                ScanRun.organization_id == source_job.organization_id,
            )
        )
        if run is not None and run.status in {ScanRunStatus.PENDING, ScanRunStatus.RUNNING}:
            run.status = ScanRunStatus.FAILED
            run.finished_at = utc_now()
            run.error_summary = terminal_job.last_error_code
            db.commit()


def _uuid_value(payload: dict[str, Any], key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError):
        raise AppError("invalid_job_payload", "The job payload is invalid.", 409) from None


def _optional_uuid(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    value = payload.get(key)
    return _uuid_value(payload, key) if value is not None else None


def main() -> None:
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    worker = JobWorker(SessionLocal, settings, worker_id)

    def stop(_signum: int, _frame: object) -> None:
        worker.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker.run_forever()


if __name__ == "__main__":
    main()
