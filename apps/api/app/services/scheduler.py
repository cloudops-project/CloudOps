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
from app.models.enums import PlatformJobType, ScanRunStatus, ScanRunTrigger
from app.security.rbac import Capability
from app.services.common import record_audit
from app.services.organizations import OrganizationService
from app.services.platform_jobs import PlatformJobService

MAX_ERROR_SUMMARY_LENGTH = 500


class SchedulerService:
    """Replica-safe scheduler that only persists queue work; it never scans inline."""

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
        commit: bool = True,
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
        job, _created = PlatformJobService(self.db).enqueue(
            organization_id=organization_id,
            job_type=PlatformJobType.SCHEDULED_SCAN,
            reference_id=run.id,
            idempotency_key=(
                f"scan-run:{run.id}"
                if trigger == ScanRunTrigger.MANUAL
                else f"schedule:{schedule.id}:{(schedule.next_run_at or utc_now()).isoformat()}"
            ),
            payload={
                "scan_run_id": str(run.id),
                "actor_user_id": str(actor.id),
                "schedule_id": str(schedule.id),
            },
            actor_user_id=actor.id if trigger == ScanRunTrigger.MANUAL else None,
        )
        record_audit(
            self.db,
            "scheduler.run.enqueued",
            "scan_run",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=run.id,
            metadata={"trigger": trigger.value, "platform_job_id": str(job.id)},
        )
        if commit:
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
            .order_by(ScanSchedule.next_run_at, ScanSchedule.id)
            .limit(self.settings.scheduler_batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        runs: list[ScanRun] = []
        for schedule in due:
            actor = (
                self.db.get(User, schedule.created_by_user_id)
                if schedule.created_by_user_id
                else None
            )
            if actor is None:
                schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
                continue
            occurrence = schedule.next_run_at
            try:
                run = self.run_schedule(
                    schedule.organization_id,
                    schedule.id,
                    actor,
                    trigger=ScanRunTrigger.SCHEDULED,
                    commit=False,
                )
                runs.append(run)
                schedule.last_enqueued_at = occurrence
                assert occurrence is not None
                schedule.next_run_at = occurrence + timedelta(
                    minutes=schedule.interval_minutes
                )
            except ConflictError:
                # Another run is already active for this account; the next
                # tick will retry once it clears. Not a worker failure.
                continue
        self.db.commit()
        return runs
