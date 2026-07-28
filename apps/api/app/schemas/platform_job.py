from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import PlatformJobStatus, PlatformJobType
from app.schemas.common import ApiModel


class PlatformJobResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    job_type: PlatformJobType
    status: PlatformJobStatus
    reference_id: uuid.UUID
    priority: int
    attempt_count: int
    max_attempts: int
    scheduled_at: datetime
    available_at: datetime
    leased_at: datetime | None
    lease_generation: int
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    dead_lettered_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    result_reference: str | None
    correlation_id: uuid.UUID
    parent_job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PlatformJobListResponse(ApiModel):
    items: list[PlatformJobResponse]
    total: int
    page: int
    page_size: int


class PlatformJobCountsResponse(ApiModel):
    counts: dict[str, int]
