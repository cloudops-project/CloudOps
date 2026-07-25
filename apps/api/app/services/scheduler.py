from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import utc_now
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import AWSAccount, ScanRun, ScanSchedule, User
from app.models.enums import AuditResult, ScanRunStatus, ScanRunTrigger
from app.security.rbac import Capability
from app.services.common import record_audit
from app.services.discovery import DiscoveryOrchestrator
from app.services.evaluations import EvaluationService
from app.services.organizations import OrganizationService

MAX_ERROR_SUMMARY_LENGTH = 500


class SchedulerService:
    """Deterministic scheduler foundation. A schedule only records a cadence
    for an AWS account; running a schedule always delegates to the existing
    DiscoveryOrchestrator and EvaluationService, so this service never makes
    a boto3 call or a real AWS mutation itself."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _get_account(self, organization_id: uuid.UUID, account_id: uuid.UUID) -> AWSAccount:
        account = self.db.scalar(
            select(AWSAccount).where(
                AWSAccount.id == account_id,
                AWSAccount.organization_id == organization_id,
            )
        )
        if account is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        return account

    def _get_scoped(self, organization_id: uuid.UUID, schedule_id: uuid.UUID) -> ScanSchedule:
        schedule = self.db.scalar(
            select(ScanSchedule).where(
                ScanSchedule.id == schedule_id,
                ScanSchedule.organization_id == organization_id,
            )
        )
        if schedule is None:
            raise NotFoundError("scan_schedule_not_found", "Scan schedule was not found.")
        return schedule

    def create_schedule(
        self,
        organization_id: uuid.UUID,
        account_id: uuid.UUID,
        actor: User,
        *,
        name: str,
        interval_minutes: int,
    ) -> ScanSchedule:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.SCHEDULE_MANAGE
        )
        self._get_account(organization_id, account_id)
        now = utc_now()
        schedule = ScanSchedule(
            organization_id=organization_id,
            aws_account_id=account_id,
            name=name,
            interval_minutes=interval_minutes,
            created_by_user_id=actor.id,
            next_run_at=now + timedelta(minutes=interval_minutes),
        )
        self.db.add(schedule)
        self.db.flush()
        record_audit(
            self.db,
            "scheduler.schedule.created",
            "scan_schedule",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=schedule.id,
        )
        self.db.commit()
        return schedule

    def set_enabled(
        self, organization_id: uuid.UUID, schedule_id: uuid.UUID, actor: User, *, enabled: bool
    ) -> ScanSchedule:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.SCHEDULE_MANAGE
        )
        schedule = self._get_scoped(organization_id, schedule_id)
        if schedule.enabled == enabled:
            return schedule
        schedule.enabled = enabled
        if enabled:
            schedule.next_run_at = utc_now() + timedelta(minutes=schedule.interval_minutes)
        else:
            schedule.next_run_at = None
        record_audit(
            self.db,
            "scheduler.schedule.enabled" if enabled else "scheduler.schedule.disabled",
            "scan_schedule",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=schedule.id,
        )
        self.db.commit()
        return schedule

    def delete_schedule(
        self, organization_id: uuid.UUID, schedule_id: uuid.UUID, actor: User
    ) -> None:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.SCHEDULE_MANAGE
        )
        schedule = self._get_scoped(organization_id, schedule_id)
        self.db.delete(schedule)
        record_audit(
            self.db,
            "scheduler.schedule.deleted",
            "scan_schedule",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=schedule_id,
        )
        self.db.commit()

    def run_schedule(
        self,
        organization_id: uuid.UUID,
        schedule_id: uuid.UUID,
        actor: User,
        *,
        trigger: ScanRunTrigger,
    ) -> ScanRun:
        schedule = self._get_scoped(organization_id, schedule_id)
        if trigger == ScanRunTrigger.MANUAL:
            OrganizationService(self.db).require_capability(
                organization_id, actor.id, Capability.SCHEDULE_MANAGE
            )
        if not schedule.enabled:
            raise ConflictError("schedule_disabled", "This schedule is disabled.")

        run = ScanRun(
            organization_id=organization_id,
            aws_account_id=schedule.aws_account_id,
            schedule_id=schedule.id,
            trigger=trigger,
            status=ScanRunStatus.PENDING,
        )
        try:
            with self.db.begin_nested():
                self.db.add(run)
                self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "scan_run_already_active", "A scan is already active for this account."
            ) from exc
        record_audit(
            self.db,
            "scheduler.run.started",
            "scan_run",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=run.id,
            metadata={"trigger": trigger.value},
        )
        self.db.commit()

        run.status = ScanRunStatus.RUNNING
        run.started_at = utc_now()
        self.db.commit()

        try:
            discovery_job = DiscoveryOrchestrator(self.db, self.settings).start(
                schedule.aws_account_id, actor
            )
            run.discovery_job_id = discovery_job.id
            evaluation_job = EvaluationService(self.db).start(
                schedule.aws_account_id, actor, discovery_job_id=discovery_job.id
            )
            run.evaluation_job_id = evaluation_job.id
            run.status = ScanRunStatus.COMPLETED
            run.finished_at = utc_now()
            record_audit(
                self.db,
                "scheduler.run.completed",
                "scan_run",
                organization_id=organization_id,
                actor_user_id=actor.id,
                resource_id=run.id,
            )
        except (ConflictError, NotFoundError) as exc:
            run.status = ScanRunStatus.FAILED
            run.finished_at = utc_now()
            run.error_summary = exc.message[:MAX_ERROR_SUMMARY_LENGTH]
            record_audit(
                self.db,
                "scheduler.run.failed",
                "scan_run",
                organization_id=organization_id,
                actor_user_id=actor.id,
                resource_id=run.id,
                result=AuditResult.FAILED,
                metadata={"reason": exc.code},
            )

        schedule.last_run_at = run.finished_at
        schedule.next_run_at = (run.finished_at or utc_now()) + timedelta(
            minutes=schedule.interval_minutes
        )
        self.db.commit()
        return run

    def run_due_schedules(self) -> list[ScanRun]:
        """Worker entry point. Finds enabled schedules whose next_run_at has
        elapsed and runs each one, acting as the schedule's creator (mirrors
        the `started_by_user_id` pattern already used by discovery/evaluation
        jobs). A schedule whose creator no longer resolves to a user is
        skipped rather than run with no accountable actor."""
        now = utc_now()
        due = self.db.scalars(
            select(ScanSchedule).where(
                ScanSchedule.enabled.is_(True),
                ScanSchedule.next_run_at.is_not(None),
                ScanSchedule.next_run_at <= now,
            )
        ).all()
        runs: list[ScanRun] = []
        for schedule in due:
            actor = (
                self.db.get(User, schedule.created_by_user_id)
                if schedule.created_by_user_id
                else None
            )
            if actor is None:
                continue
            try:
                runs.append(
                    self.run_schedule(
                        schedule.organization_id,
                        schedule.id,
                        actor,
                        trigger=ScanRunTrigger.SCHEDULED,
                    )
                )
            except ConflictError:
                # Another run is already active for this account; the next
                # tick will retry once it clears. Not a worker failure.
                continue
        return runs
