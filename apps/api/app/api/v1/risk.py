from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.sql import Select

from app.dependencies.auth import CurrentUser, DbSession
from app.exceptions.errors import AppError, NotFoundError
from app.models import (
    AccountRiskSnapshot,
    Asset,
    AssetRiskContext,
    CompensatingControl,
    Finding,
    FindingRiskSnapshot,
    OrganizationRiskSnapshot,
    RiskAssessment,
    RiskScoringPolicy,
)
from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingSeverity,
    FindingStatus,
    RiskAssessmentStatus,
    RiskEnvironment,
    RiskPriority,
)
from app.schemas.risk import (
    AccountRiskResponse,
    CompensatingControlRequest,
    CompensatingControlResponse,
    FindingRiskListItem,
    FindingRiskListResponse,
    FindingRiskResponse,
    OrganizationRiskResponse,
    RiskAssessmentListResponse,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskContextRequest,
    RiskContextResponse,
    RiskPolicyResponse,
    RiskSummaryResponse,
)
from app.security.rbac import Capability
from app.services.common import record_audit
from app.services.organizations import OrganizationService
from app.services.risk import RiskService

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_read(db: DbSession, user: CurrentUser, organization_id: uuid.UUID) -> None:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.RISK_READ)


@router.get("/risk/policies", response_model=list[RiskPolicyResponse])
def policies(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[RiskPolicyResponse]:
    _require_read(db, user, organization_id)
    RiskService(db).ensure_policy()
    db.commit()
    return [
        RiskPolicyResponse.model_validate(item)
        for item in db.scalars(
            select(RiskScoringPolicy).order_by(
                RiskScoringPolicy.key, RiskScoringPolicy.version.desc()
            )
        ).all()
    ]


@router.post(
    "/risk/assess",
    response_model=RiskAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assess(
    payload: RiskAssessmentRequest,
    user: CurrentUser,
    db: DbSession,
) -> RiskAssessment:
    try:
        return RiskService(db).assess(
            payload.organization_id,
            user,
            aws_account_id=payload.aws_account_id,
            evaluation_time=payload.evaluation_time,
        )
    except AppError:
        raise
    except Exception:
        db.rollback()
        record_audit(
            db,
            "risk.assessment.failed",
            "risk_assessment",
            organization_id=payload.organization_id,
            actor_user_id=user.id,
            metadata={
                "aws_account_id": (str(payload.aws_account_id) if payload.aws_account_id else None),
                "error_code": "risk_persistence_failed",
            },
        )
        db.commit()
        logger.error(
            "risk.assessment.failed",
            extra={
                "event_name": "risk.assessment.failed",
                "organization_id": str(payload.organization_id),
                "error_code": "risk_persistence_failed",
            },
        )
        raise


@router.get("/risk/assessments", response_model=RiskAssessmentListResponse)
def assessments(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID | None = None,
    assessment_status: RiskAssessmentStatus | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RiskAssessmentListResponse:
    _require_read(db, user, organization_id)
    statement = select(RiskAssessment).where(RiskAssessment.organization_id == organization_id)
    if aws_account_id:
        statement = statement.where(RiskAssessment.aws_account_id == aws_account_id)
    if assessment_status:
        statement = statement.where(RiskAssessment.status == assessment_status)
    if started_after:
        statement = statement.where(RiskAssessment.started_at > started_after)
    if started_before:
        statement = statement.where(RiskAssessment.started_at < started_before)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = db.scalars(
        statement.order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return RiskAssessmentListResponse(
        items=[RiskAssessmentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/risk/assessments/{assessment_id}", response_model=RiskAssessmentResponse)
def assessment_detail(
    assessment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RiskAssessment:
    _require_read(db, user, organization_id)
    item = db.scalar(
        select(RiskAssessment).where(
            RiskAssessment.id == assessment_id,
            RiskAssessment.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("risk_assessment_not_found", "Risk assessment was not found.")
    return item


@router.get("/risk/summary", response_model=RiskSummaryResponse)
def summary(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RiskSummaryResponse:
    _require_read(db, user, organization_id)
    assessment = db.scalar(
        select(RiskAssessment)
        .where(
            RiskAssessment.organization_id == organization_id,
            RiskAssessment.status == RiskAssessmentStatus.COMPLETED,
        )
        .order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id)
    )
    if assessment is None:
        return RiskSummaryResponse(
            current=None,
            assessment=None,
            highest_risk_accounts=[],
            highest_risk_findings=[],
            highest_risk_assets=[],
            trend=[],
        )
    current = db.scalar(
        select(OrganizationRiskSnapshot).where(
            OrganizationRiskSnapshot.assessment_id == assessment.id
        )
    )
    accounts = db.scalars(
        select(AccountRiskSnapshot)
        .where(AccountRiskSnapshot.assessment_id == assessment.id)
        .order_by(AccountRiskSnapshot.risk_score.desc(), AccountRiskSnapshot.aws_account_id)
        .limit(10)
    ).all()
    findings = _finding_items(
        db,
        select(FindingRiskSnapshot)
        .where(FindingRiskSnapshot.assessment_id == assessment.id)
        .order_by(
            FindingRiskSnapshot.risk_score.desc(),
            FindingRiskSnapshot.business_impact_points.desc(),
            FindingRiskSnapshot.finding_id,
        )
        .limit(10),
    )
    assets = [item for item in findings if item.asset_id is not None][:10]
    trend = db.scalars(
        select(OrganizationRiskSnapshot)
        .where(OrganizationRiskSnapshot.organization_id == organization_id)
        .order_by(OrganizationRiskSnapshot.evaluation_time.desc())
        .limit(30)
    ).all()
    return RiskSummaryResponse(
        current=OrganizationRiskResponse.model_validate(current) if current else None,
        assessment=RiskAssessmentResponse.model_validate(assessment),
        highest_risk_accounts=[AccountRiskResponse.model_validate(item) for item in accounts],
        highest_risk_findings=findings,
        highest_risk_assets=assets,
        trend=[OrganizationRiskResponse.model_validate(item) for item in trend],
    )


@router.get("/risk/findings", response_model=FindingRiskListResponse)
def risk_findings(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    severity: FindingSeverity | None = None,
    priority: RiskPriority | None = None,
    minimum_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    maximum_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    service: Annotated[str | None, Query(max_length=32)] = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
    environment: RiskEnvironment | None = None,
    business_impact: BusinessImpact | None = None,
    data_sensitivity: DataSensitivity | None = None,
    finding_status: FindingStatus | None = None,
    suppressed: bool | None = None,
    rule_key: Annotated[str | None, Query(max_length=160)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    evaluated_after: datetime | None = None,
    evaluated_before: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FindingRiskListResponse:
    _require_read(db, user, organization_id)
    if minimum_score is not None and maximum_score is not None and minimum_score > maximum_score:
        raise AppError(
            "invalid_score_range",
            "minimum_score must not exceed maximum_score.",
            422,
        )
    latest = db.scalar(
        select(RiskAssessment.id)
        .where(
            RiskAssessment.organization_id == organization_id,
            RiskAssessment.status == RiskAssessmentStatus.COMPLETED,
        )
        .order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id)
    )
    if latest is None:
        return FindingRiskListResponse(items=[], total=0, page=page, page_size=page_size)
    statement = (
        select(FindingRiskSnapshot)
        .join(Finding, Finding.id == FindingRiskSnapshot.finding_id)
        .outerjoin(Asset, Asset.id == FindingRiskSnapshot.asset_id)
        .outerjoin(
            AssetRiskContext,
            AssetRiskContext.asset_id == FindingRiskSnapshot.asset_id,
        )
        .where(
            FindingRiskSnapshot.assessment_id == latest,
            FindingRiskSnapshot.organization_id == organization_id,
        )
    )
    if aws_account_id:
        statement = statement.where(FindingRiskSnapshot.aws_account_id == aws_account_id)
    if asset_id:
        statement = statement.where(FindingRiskSnapshot.asset_id == asset_id)
    if severity:
        statement = statement.where(Finding.severity == severity)
    if priority:
        statement = statement.where(FindingRiskSnapshot.priority == priority)
    if minimum_score is not None:
        statement = statement.where(FindingRiskSnapshot.risk_score >= minimum_score)
    if maximum_score is not None:
        statement = statement.where(FindingRiskSnapshot.risk_score <= maximum_score)
    if service:
        statement = statement.where(Finding.rule_key.startswith(f"{service.upper()}_"))
    if region:
        statement = statement.where(Asset.region == region)
    if environment:
        statement = statement.where(AssetRiskContext.environment == environment)
    if business_impact:
        statement = statement.where(AssetRiskContext.business_impact == business_impact)
    if data_sensitivity:
        statement = statement.where(AssetRiskContext.data_sensitivity == data_sensitivity)
    if finding_status:
        statement = statement.where(Finding.status == finding_status)
    if suppressed is not None:
        statement = statement.where(
            Finding.status == (FindingStatus.SUPPRESSED if suppressed else FindingStatus.OPEN)
        )
    if rule_key:
        statement = statement.where(Finding.rule_key == rule_key)
    if evaluated_after:
        statement = statement.where(FindingRiskSnapshot.evaluation_time > evaluated_after)
    if evaluated_before:
        statement = statement.where(FindingRiskSnapshot.evaluation_time < evaluated_before)
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if escaped:
            statement = statement.where(
                Finding.rule_key.ilike(f"%{escaped}%", escape="\\")
                | Finding.category.ilike(f"%{escaped}%", escape="\\")
                | Asset.name.ilike(f"%{escaped}%", escape="\\")
            )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    severity_order = case(
        {
            FindingSeverity.CRITICAL: 4,
            FindingSeverity.HIGH: 3,
            FindingSeverity.MEDIUM: 2,
            FindingSeverity.LOW: 1,
        },
        value=Finding.severity,
        else_=0,
    )
    items = _finding_items(
        db,
        statement.order_by(
            FindingRiskSnapshot.risk_score.desc(),
            severity_order.desc(),
            FindingRiskSnapshot.business_impact_points.desc(),
            Finding.first_seen_at,
            Finding.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size),
    )
    return FindingRiskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/risk/findings/{finding_id}", response_model=FindingRiskResponse)
def risk_finding_detail(
    finding_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FindingRiskSnapshot:
    _require_read(db, user, organization_id)
    item = db.scalar(
        select(FindingRiskSnapshot)
        .join(RiskAssessment)
        .where(
            FindingRiskSnapshot.finding_id == finding_id,
            FindingRiskSnapshot.organization_id == organization_id,
            RiskAssessment.status == RiskAssessmentStatus.COMPLETED,
        )
        .order_by(FindingRiskSnapshot.evaluation_time.desc(), FindingRiskSnapshot.id)
    )
    if item is None:
        raise NotFoundError("finding_risk_not_found", "Finding risk was not found.")
    return item


@router.get("/risk/accounts/{account_id}", response_model=AccountRiskResponse)
def account_detail(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AccountRiskSnapshot:
    _require_read(db, user, organization_id)
    item = db.scalar(
        select(AccountRiskSnapshot)
        .where(
            AccountRiskSnapshot.aws_account_id == account_id,
            AccountRiskSnapshot.organization_id == organization_id,
        )
        .order_by(AccountRiskSnapshot.evaluation_time.desc(), AccountRiskSnapshot.id)
    )
    if item is None:
        raise NotFoundError("account_risk_not_found", "Account risk was not found.")
    return item


@router.get("/risk/assets/{asset_id}", response_model=list[FindingRiskResponse])
def asset_detail(
    asset_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[FindingRiskResponse]:
    _require_read(db, user, organization_id)
    exists = db.scalar(
        select(Asset.id).where(Asset.id == asset_id, Asset.organization_id == organization_id)
    )
    if exists is None:
        raise NotFoundError("asset_not_found", "Asset was not found.")
    latest = db.scalar(
        select(RiskAssessment.id)
        .where(
            RiskAssessment.organization_id == organization_id,
            RiskAssessment.status == RiskAssessmentStatus.COMPLETED,
        )
        .order_by(RiskAssessment.evaluation_time.desc(), RiskAssessment.id)
    )
    if latest is None:
        return []
    return [
        FindingRiskResponse.model_validate(item)
        for item in db.scalars(
            select(FindingRiskSnapshot)
            .where(
                FindingRiskSnapshot.assessment_id == latest,
                FindingRiskSnapshot.asset_id == asset_id,
            )
            .order_by(FindingRiskSnapshot.risk_score.desc(), FindingRiskSnapshot.finding_id)
        ).all()
    ]


@router.get("/risk/context", response_model=RiskContextResponse)
def get_context(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
) -> AssetRiskContext:
    _require_read(db, user, organization_id)
    asset_filter = (
        AssetRiskContext.asset_id.is_(None)
        if asset_id is None
        else AssetRiskContext.asset_id == asset_id
    )
    item = db.scalar(
        select(AssetRiskContext).where(
            AssetRiskContext.organization_id == organization_id,
            AssetRiskContext.aws_account_id == aws_account_id,
            asset_filter,
        )
    )
    if item is None:
        raise NotFoundError("risk_context_not_found", "Risk context was not found.")
    return item


@router.put("/risk/context", response_model=RiskContextResponse)
def put_context(
    payload: RiskContextRequest,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AssetRiskContext:
    return RiskService(db).update_context(
        organization_id,
        user,
        aws_account_id=payload.aws_account_id,
        asset_id=payload.asset_id,
        criticality=payload.criticality,
        environment=payload.environment,
        business_impact=payload.business_impact,
        data_sensitivity=payload.data_sensitivity,
        expected_version=payload.expected_version,
    )


@router.post(
    "/risk/findings/{finding_id}/compensating-controls",
    response_model=CompensatingControlResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_control(
    finding_id: uuid.UUID,
    payload: CompensatingControlRequest,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> CompensatingControl:
    return RiskService(db).add_compensating_control(
        organization_id,
        finding_id,
        user,
        reason=payload.reason,
        score_adjustment=payload.score_adjustment,
        expires_at=payload.expires_at,
    )


@router.delete(
    "/risk/compensating-controls/{control_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_control(
    control_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> Response:
    RiskService(db).remove_compensating_control(organization_id, control_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _finding_items(
    db: DbSession, statement: Select[tuple[FindingRiskSnapshot]]
) -> list[FindingRiskListItem]:
    snapshots = list(db.scalars(statement).all())
    if not snapshots:
        return []
    finding_ids = [item.finding_id for item in snapshots]
    findings = {
        item.id: item
        for item in db.scalars(select(Finding).where(Finding.id.in_(finding_ids))).all()
    }
    asset_ids = [item.asset_id for item in snapshots if item.asset_id is not None]
    assets = {
        item.id: item
        for item in (
            db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all() if asset_ids else []
        )
    }
    contexts = {
        item.asset_id: item
        for item in (
            db.scalars(
                select(AssetRiskContext).where(AssetRiskContext.asset_id.in_(asset_ids))
            ).all()
            if asset_ids
            else []
        )
    }
    result: list[FindingRiskListItem] = []
    for snapshot in snapshots:
        finding = findings[snapshot.finding_id]
        asset = assets.get(snapshot.asset_id) if snapshot.asset_id is not None else None
        context = contexts.get(snapshot.asset_id) if snapshot.asset_id is not None else None
        data = FindingRiskResponse.model_validate(snapshot).model_dump()
        result.append(
            FindingRiskListItem(
                **data,
                severity=finding.severity,
                rule_key=finding.rule_key,
                finding_status=finding.status,
                asset_name=asset.name if asset else None,
                service=finding.rule_key.split("_", 1)[0].casefold(),
                region=asset.region if asset else None,
                business_impact=(context.business_impact if context else BusinessImpact.UNKNOWN),
            )
        )
    return result
