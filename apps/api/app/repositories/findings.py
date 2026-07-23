from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import EvaluationJob, Finding
from app.models.enums import EvaluationJobStatus, FindingSeverity, FindingStatus


class EvaluationJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_sequence(self, account_id: uuid.UUID) -> int:
        current = self.db.scalar(
            select(func.max(EvaluationJob.sequence)).where(
                EvaluationJob.aws_account_id == account_id
            )
        )
        return int(current or 0) + 1

    def active_for_account(self, account_id: uuid.UUID) -> EvaluationJob | None:
        return self.db.scalar(
            select(EvaluationJob).where(
                EvaluationJob.aws_account_id == account_id,
                EvaluationJob.status.in_(
                    [EvaluationJobStatus.PENDING, EvaluationJobStatus.RUNNING]
                ),
            )
        )

    def list(
        self, organization_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[EvaluationJob], int]:
        filters = [EvaluationJob.organization_id == organization_id]
        total = int(
            self.db.scalar(select(func.count()).select_from(EvaluationJob).where(*filters)) or 0
        )
        items = list(
            self.db.scalars(
                select(EvaluationJob)
                .where(*filters)
                .order_by(EvaluationJob.created_at.desc(), EvaluationJob.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def get(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> EvaluationJob | None:
        return self.db.scalar(
            select(EvaluationJob).where(
                EvaluationJob.organization_id == organization_id,
                EvaluationJob.id == job_id,
            )
        )


class FindingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def for_rule(
        self, account_id: uuid.UUID, rule_key: str, asset_id: uuid.UUID | None
    ) -> Finding | None:
        asset_filter = (
            Finding.asset_id.is_(None) if asset_id is None else Finding.asset_id == asset_id
        )
        return self.db.scalar(
            select(Finding)
            .where(
                Finding.aws_account_id == account_id,
                Finding.rule_key == rule_key,
                asset_filter,
            )
            .with_for_update()
        )

    def list(
        self,
        organization_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None,
        severity: FindingSeverity | None,
        status: FindingStatus | None,
        rule_key: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Finding], int]:
        filters = [Finding.organization_id == organization_id]
        if account_id:
            filters.append(Finding.aws_account_id == account_id)
        if severity:
            filters.append(Finding.severity == severity)
        if status:
            filters.append(Finding.status == status)
        if rule_key:
            filters.append(Finding.rule_key == rule_key)
        if search:
            value = f"%{search.strip()}%"
            filters.append(or_(Finding.rule_key.ilike(value), Finding.category.ilike(value)))
        total = int(self.db.scalar(select(func.count()).select_from(Finding).where(*filters)) or 0)
        items = list(
            self.db.scalars(
                select(Finding)
                .where(*filters)
                .order_by(Finding.last_seen_at.desc(), Finding.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def get(self, organization_id: uuid.UUID, finding_id: uuid.UUID) -> Finding | None:
        return self.db.scalar(
            select(Finding)
            .where(Finding.organization_id == organization_id, Finding.id == finding_id)
            .with_for_update()
        )

    def summary(
        self, organization_id: uuid.UUID
    ) -> Sequence[tuple[FindingSeverity, FindingStatus, int]]:
        return (
            self.db.execute(
                select(Finding.severity, Finding.status, func.count())
                .where(Finding.organization_id == organization_id)
                .group_by(Finding.severity, Finding.status)
            )
            .tuples()
            .all()
        )
