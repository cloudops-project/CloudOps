from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import ScanRunStatus, ScanRunTrigger
from app.schemas.common import ApiModel


class ScanScheduleCreate(ApiModel):
    aws_account_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    interval_minutes: int = Field(ge=15, le=10_080)


class ScanScheduleResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    name: str
    interval_minutes: int
    enabled: bool
    created_by_user_id: uuid.UUID | None
    last_run_at: datetime | None
    last_enqueued_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScanScheduleListResponse(ApiModel):
    items: list[ScanScheduleResponse]
    total: int
    page: int
    page_size: int


class ScanRunResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    schedule_id: uuid.UUID | None
    trigger: ScanRunTrigger
    status: ScanRunStatus
    discovery_job_id: uuid.UUID | None
    evaluation_job_id: uuid.UUID | None
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScanRunListResponse(ApiModel):
    items: list[ScanRunResponse]
    total: int
    page: int
    page_size: int
