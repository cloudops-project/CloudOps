from __future__ import annotations

import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import AppSettings, CurrentUser, DbSession, UserRateLimiter
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Asset, DiscoveryJob
from app.models.enums import AssetType, AWSAccountStatus, PlatformJobType
from app.repositories.assets import AssetRepository, DiscoveryJobRepository
from app.repositories.data import Repository
from app.schemas.discovery import (
    AssetListResponse,
    AssetResponse,
    AssetSummaryItem,
    AssetSummaryResponse,
    DiscoveryJobListResponse,
    DiscoveryJobResponse,
)
from app.schemas.platform_job import PlatformJobResponse
from app.security.rbac import Capability, role_has_capability
from app.services.discovery import json_safe
from app.services.organizations import OrganizationService
from app.services.platform_jobs import PlatformJobService

router = APIRouter()
_start_rate_limit = UserRateLimiter("discovery_start", limit=5, window_seconds=60)


def _asset_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        organization_id=asset.organization_id,
        aws_account_id=asset.aws_account_id,
        asset_type=asset.asset_type,
        resource_id=asset.resource_id,
        arn=asset.arn,
        name=asset.name,
        region=asset.region,
        status=asset.status,
        tags=cast(dict[str, str], json_safe(asset.tags)),
        metadata=cast(dict[str, Any], json_safe(asset.metadata_json)),
        first_seen_at=asset.first_seen_at,
        last_seen_at=asset.last_seen_at,
        is_active=asset.is_active,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.post(
    "/aws/accounts/{account_id}/discover",
    response_model=PlatformJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_start_rate_limit)],
)
def start_discovery(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> PlatformJobResponse:
    result = Repository(db).aws_account_for_user(account_id, user.id)
    if result is None:
        raise NotFoundError("aws_account_not_found", "AWS account was not found.")
    account, membership = result
    if not role_has_capability(membership.role, Capability.DISCOVERY_START):
        from app.exceptions.errors import ForbiddenError

        raise ForbiddenError()
    if account.connection_status != AWSAccountStatus.CONNECTED:
        raise ConflictError(
            "aws_account_not_connected", "Only connected AWS accounts can run discovery."
        )
    job, _created = PlatformJobService(db).enqueue(
        organization_id=account.organization_id,
        job_type=PlatformJobType.DISCOVERY,
        reference_id=account.id,
        idempotency_key=f"manual-discovery:{uuid.uuid4()}",
        payload={"actor_user_id": str(user.id), "account_id": str(account.id)},
        actor_user_id=user.id,
    )
    db.commit()
    return PlatformJobResponse.model_validate(job)


@router.get("/discovery/jobs", response_model=DiscoveryJobListResponse)
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DiscoveryJobListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.ASSETS_READ)
    items, total = DiscoveryJobRepository(db).list(organization_id, page, page_size)
    return DiscoveryJobListResponse(
        items=[DiscoveryJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/discovery/jobs/{job_id}", response_model=DiscoveryJobResponse)
def get_job(
    job_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> DiscoveryJob:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.ASSETS_READ)
    job = DiscoveryJobRepository(db).get(organization_id, job_id)
    if not job:
        raise NotFoundError("discovery_job_not_found", "Discovery job was not found.")
    return job


@router.get("/assets", response_model=AssetListResponse)
def list_assets(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID | None = None,
    asset_type: AssetType | None = None,
    region: str | None = None,
    asset_status: Annotated[str | None, Query(alias="status", max_length=128)] = None,
    is_active: bool | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AssetListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.ASSETS_READ)
    items, total = AssetRepository(db).list(
        organization_id,
        account_id=aws_account_id,
        asset_type=asset_type,
        region=region,
        status=asset_status,
        is_active=is_active,
        search=search,
        page=page,
        page_size=page_size,
    )
    return AssetListResponse(
        items=[_asset_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/assets/summary", response_model=AssetSummaryResponse)
def asset_summary(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AssetSummaryResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.ASSETS_READ)
    values: dict[AssetType, dict[bool, int]] = {}
    for asset_type, active, count in AssetRepository(db).summary(organization_id):
        values.setdefault(asset_type, {})[active] = count
    by_type = [
        AssetSummaryItem(
            asset_type=asset_type,
            active=counts.get(True, 0),
            stale=counts.get(False, 0),
        )
        for asset_type, counts in sorted(values.items(), key=lambda item: item[0].value)
    ]
    active_total = sum(item.active for item in by_type)
    stale_total = sum(item.stale for item in by_type)
    return AssetSummaryResponse(
        total=active_total + stale_total,
        active=active_total,
        stale=stale_total,
        by_type=by_type,
    )


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AssetResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.ASSETS_READ)
    asset = AssetRepository(db).get(organization_id, asset_id)
    if not asset:
        raise NotFoundError("asset_not_found", "Asset was not found.")
    return _asset_response(asset)
