from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession
from app.models import PlatformJob
from app.models.enums import PlatformJobStatus, PlatformJobType
from app.schemas.platform_job import (
    PlatformJobCountsResponse,
    PlatformJobListResponse,
    PlatformJobResponse,
)
from app.security.rbac import Capability
from app.services.organizations import OrganizationService
from app.services.platform_jobs import PlatformJobService

router = APIRouter()


def _require_read(db: DbSession, user: CurrentUser, organization_id: uuid.UUID) -> None:
    OrganizationService(db).require_capability(
        organization_id, user.id, Capability.JOBS_READ
    )


@router.get("/jobs", response_model=PlatformJobListResponse)
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    job_type: PlatformJobType | None = None,
    status_filter: Annotated[PlatformJobStatus | None, Query(alias="status")] = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PlatformJobListResponse:
    _require_read(db, user, organization_id)
    statement = select(PlatformJob).where(
        PlatformJob.organization_id == organization_id
    )
    if job_type is not None:
        statement = statement.where(PlatformJob.job_type == job_type)
    if status_filter is not None:
        statement = statement.where(PlatformJob.status == status_filter)
    if created_after is not None:
        statement = statement.where(PlatformJob.created_at >= created_after)
    if created_before is not None:
        statement = statement.where(PlatformJob.created_at <= created_before)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(PlatformJob.created_at.desc(), PlatformJob.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PlatformJobListResponse(
        items=[PlatformJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/counts", response_model=PlatformJobCountsResponse)
def job_counts(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> PlatformJobCountsResponse:
    _require_read(db, user, organization_id)
    return PlatformJobCountsResponse(
        counts=PlatformJobService(db).counts(organization_id)
    )


@router.get("/jobs/{job_id}", response_model=PlatformJobResponse)
def job_detail(
    job_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> PlatformJob:
    _require_read(db, user, organization_id)
    return PlatformJobService(db).get_scoped(organization_id, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=PlatformJobResponse)
def cancel_job(
    job_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> PlatformJob:
    return PlatformJobService(db).cancel(organization_id, job_id, user)


@router.post("/jobs/{job_id}/requeue", response_model=PlatformJobResponse)
def requeue_job(
    job_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> PlatformJob:
    return PlatformJobService(db).requeue(organization_id, job_id, user)
