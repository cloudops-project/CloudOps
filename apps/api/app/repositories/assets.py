from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Asset, DiscoveryJob
from app.models.enums import AssetType, DiscoveryJobStatus


class AssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def by_identity(
        self, account_id: uuid.UUID, asset_type: AssetType, resource_id: str
    ) -> Asset | None:
        return self.db.scalar(
            select(Asset).where(
                Asset.aws_account_id == account_id,
                Asset.asset_type == asset_type,
                Asset.resource_id == resource_id,
            )
        )

    def deactivate_missing(
        self,
        account_id: uuid.UUID,
        asset_types: set[AssetType],
        seen: set[tuple[AssetType, str]],
        at: datetime,
    ) -> int:
        assets = list(
            self.db.scalars(
                select(Asset).where(
                    Asset.aws_account_id == account_id,
                    Asset.asset_type.in_(asset_types),
                    Asset.is_active.is_(True),
                )
            )
        )
        count = 0
        for asset in assets:
            if (asset.asset_type, asset.resource_id) not in seen:
                asset.is_active = False
                asset.updated_at = at
                count += 1
        return count

    def list(
        self,
        organization_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None,
        asset_type: AssetType | None,
        region: str | None,
        status: str | None,
        is_active: bool | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Asset], int]:
        filters = [Asset.organization_id == organization_id]
        if account_id:
            filters.append(Asset.aws_account_id == account_id)
        if asset_type:
            filters.append(Asset.asset_type == asset_type)
        if region:
            filters.append(Asset.region == region)
        if status:
            filters.append(Asset.status == status)
        if is_active is not None:
            filters.append(Asset.is_active == is_active)
        if search:
            value = f"%{search.strip()}%"
            filters.append(
                or_(
                    Asset.name.ilike(value),
                    Asset.resource_id.ilike(value),
                    Asset.arn.ilike(value),
                )
            )
        total = int(self.db.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0)
        statement = (
            select(Asset)
            .where(*filters)
            .order_by(Asset.last_seen_at.desc(), Asset.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total

    def get(self, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
        return self.db.scalar(
            select(Asset).where(Asset.organization_id == organization_id, Asset.id == asset_id)
        )

    def summary(self, organization_id: uuid.UUID) -> Sequence[tuple[AssetType, bool, int]]:
        statement = (
            select(Asset.asset_type, Asset.is_active, func.count())
            .where(Asset.organization_id == organization_id)
            .group_by(Asset.asset_type, Asset.is_active)
        )
        return self.db.execute(statement).tuples().all()


class DiscoveryJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, job: DiscoveryJob) -> DiscoveryJob:
        self.db.add(job)
        self.db.flush()
        return job

    def list(
        self, organization_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[DiscoveryJob], int]:
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(DiscoveryJob)
                .where(DiscoveryJob.organization_id == organization_id)
            )
            or 0
        )
        statement = (
            select(DiscoveryJob)
            .where(DiscoveryJob.organization_id == organization_id)
            .order_by(DiscoveryJob.created_at.desc(), DiscoveryJob.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement)), total

    def get(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> DiscoveryJob | None:
        return self.db.scalar(
            select(DiscoveryJob).where(
                DiscoveryJob.organization_id == organization_id,
                DiscoveryJob.id == job_id,
            )
        )

    def active_for_account(self, account_id: uuid.UUID) -> DiscoveryJob | None:
        return self.db.scalar(
            select(DiscoveryJob).where(
                DiscoveryJob.aws_account_id == account_id,
                DiscoveryJob.status.in_([DiscoveryJobStatus.PENDING, DiscoveryJobStatus.RUNNING]),
            )
        )
