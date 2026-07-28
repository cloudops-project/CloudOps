from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.dependencies.auth import AppSettings, CurrentUser, DbSession, UserRateLimiter
from app.exceptions.errors import NotFoundError
from app.models import ScanRun, ScanSchedule
from app.models.enums import ScanRunStatus, ScanRunTrigger
from app.schemas.scheduler import (
    ScanRunListResponse,
    ScanRunResponse,
    ScanScheduleCreate,
    ScanScheduleListResponse,
    ScanScheduleResponse,
)
from app.security.rbac import Capability
from app.services.organizations import OrganizationService
from app.services.scheduler import SchedulerService

router = APIRouter()
_run_rate_limit = UserRateLimiter("schedule_run", limit=5, window_seconds=60)


def _require(
    db: DbSession, user: CurrentUser, organization_id: uuid.UUID, capability: Capability
) -> None:
    OrganizationService(db).require_capability(organization_id, user.id, capability)


@router.post("/schedules", response_model=ScanScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: ScanScheduleCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanSchedule:
    schedule = SchedulerService(db, settings).create_schedule(
        organization_id,
        payload.aws_account_id,
        user,
        name=payload.name,
        interval_minutes=payload.interval_minutes,
    )
    return schedule


@router.get("/schedules", response_model=ScanScheduleListResponse)
def list_schedules(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ScanScheduleListResponse:
    _require(db, user, organization_id, Capability.SCHEDULE_READ)
    statement = select(ScanSchedule).where(ScanSchedule.organization_id == organization_id)
    if aws_account_id:
        statement = statement.where(ScanSchedule.aws_account_id == aws_account_id)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(ScanSchedule.created_at.desc(), ScanSchedule.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ScanScheduleListResponse(
        items=[ScanScheduleResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/schedules/{schedule_id}", response_model=ScanScheduleResponse)
def schedule_detail(
    schedule_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanSchedule:
    _require(db, user, organization_id, Capability.SCHEDULE_READ)
    item = db.scalar(
        select(ScanSchedule).where(
            ScanSchedule.id == schedule_id,
            ScanSchedule.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("scan_schedule_not_found", "Scan schedule was not found.")
    return item


@router.post("/schedules/{schedule_id}/enable", response_model=ScanScheduleResponse)
def enable_schedule(
    schedule_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanSchedule:
    return SchedulerService(db, settings).set_enabled(
        organization_id, schedule_id, user, enabled=True
    )


@router.post("/schedules/{schedule_id}/disable", response_model=ScanScheduleResponse)
def disable_schedule(
    schedule_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanSchedule:
    return SchedulerService(db, settings).set_enabled(
        organization_id, schedule_id, user, enabled=False
    )


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> None:
    SchedulerService(db, settings).delete_schedule(organization_id, schedule_id, user)


@router.post(
    "/schedules/{schedule_id}/run",
    response_model=ScanRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_run_rate_limit)],
)
def run_schedule_now(
    schedule_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanRun:
    return SchedulerService(db, settings).run_schedule(
        organization_id, schedule_id, user, trigger=ScanRunTrigger.MANUAL
    )


@router.get("/scan-runs", response_model=ScanRunListResponse)
def list_scan_runs(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    schedule_id: uuid.UUID | None = None,
    aws_account_id: uuid.UUID | None = None,
    status_filter: Annotated[ScanRunStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ScanRunListResponse:
    _require(db, user, organization_id, Capability.SCHEDULE_READ)
    statement = select(ScanRun).where(ScanRun.organization_id == organization_id)
    if schedule_id:
        statement = statement.where(ScanRun.schedule_id == schedule_id)
    if aws_account_id:
        statement = statement.where(ScanRun.aws_account_id == aws_account_id)
    if status_filter:
        statement = statement.where(ScanRun.status == status_filter)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(ScanRun.created_at.desc(), ScanRun.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ScanRunListResponse(
        items=[ScanRunResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/scan-runs/{run_id}", response_model=ScanRunResponse)
def scan_run_detail(
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ScanRun:
    _require(db, user, organization_id, Capability.SCHEDULE_READ)
    item = db.scalar(
        select(ScanRun).where(
            ScanRun.id == run_id,
            ScanRun.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("scan_run_not_found", "Scan run was not found.")
    return item
