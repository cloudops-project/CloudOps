from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.enums import AssetType, DiscoveryJobStatus
from app.schemas.common import ApiModel


class AssetResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    asset_type: AssetType
    resource_id: str
    arn: str | None
    name: str
    region: str
    status: str | None
    tags: dict[str, str]
    metadata: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssetListResponse(ApiModel):
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


class AssetSummaryItem(ApiModel):
    asset_type: AssetType
    active: int
    stale: int


class AssetSummaryResponse(ApiModel):
    total: int
    active: int
    stale: int
    by_type: list[AssetSummaryItem]


class DiscoveryJobResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aws_account_id: uuid.UUID
    status: DiscoveryJobStatus
    started_by_user_id: uuid.UUID
    started_at: datetime | None
    finished_at: datetime | None
    assets_discovered: int
    assets_created: int
    assets_updated: int
    assets_deactivated: int
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


class DiscoveryJobListResponse(ApiModel):
    items: list[DiscoveryJobResponse]
    total: int
    page: int
    page_size: int
