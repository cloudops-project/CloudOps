from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession
from app.exceptions.errors import AppError, NotFoundError
from app.models import (
    Asset,
    ComplianceAssessment,
    ComplianceAssessmentControl,
    ComplianceControl,
    ComplianceFramework,
    Finding,
    RuleControlMapping,
)
from app.models.enums import (
    ComplianceAssessmentStatus,
    ComplianceControlStatus,
    FindingSeverity,
)
from app.repositories.data import Repository
from app.schemas.compliance import (
    AssessmentControlResponse,
    AssessmentDetailResponse,
    AssessmentListResponse,
    AssessmentRequest,
    AssessmentResponse,
    ComplianceSummaryResponse,
    ControlFindingResponse,
    ControlResponse,
    FrameworkResponse,
    RuleControlMappingResponse,
)
from app.security.rbac import Capability
from app.services.common import record_audit
from app.services.compliance import ComplianceService
from app.services.organizations import OrganizationService

router = APIRouter()
logger = logging.getLogger(__name__)


def _read_capability(db: DbSession, user: CurrentUser, organization_id: uuid.UUID) -> None:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.COMPLIANCE_READ)


def _catalog(db: DbSession) -> ComplianceService:
    service = ComplianceService(db)
    service.ensure_catalog()
    db.commit()
    return service


@router.get("/compliance/frameworks", response_model=list[FrameworkResponse])
def frameworks(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[FrameworkResponse]:
    _read_capability(db, user, organization_id)
    _catalog(db)
    statement = (
        select(ComplianceFramework)
        .where(ComplianceFramework.enabled.is_(True))
        .order_by(ComplianceFramework.key, ComplianceFramework.version.desc())
    )
    return [FrameworkResponse.model_validate(item) for item in db.scalars(statement).all()]


@router.get("/compliance/frameworks/{framework_key}", response_model=FrameworkResponse)
def framework_detail(
    framework_key: str,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FrameworkResponse:
    _read_capability(db, user, organization_id)
    return FrameworkResponse.model_validate(_catalog(db).framework(framework_key))


@router.get(
    "/compliance/frameworks/{framework_key}/controls",
    response_model=list[ControlResponse],
)
def controls(
    framework_key: str,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[ControlResponse]:
    _read_capability(db, user, organization_id)
    service = _catalog(db)
    return [
        ControlResponse.model_validate(item)
        for item in service.controls(service.framework(framework_key))
    ]


@router.post(
    "/aws/accounts/{account_id}/compliance/assess",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assess(
    account_id: uuid.UUID,
    payload: AssessmentRequest,
    user: CurrentUser,
    db: DbSession,
) -> ComplianceAssessment:
    try:
        return ComplianceService(db).assess(
            account_id,
            user,
            payload.framework_key,
            payload.framework_version,
            payload.evaluation_job_id,
        )
    except AppError:
        raise
    except Exception:
        db.rollback()
        authorized = Repository(db).aws_account_for_user(account_id, user.id)
        if authorized is not None:
            account, _membership = authorized
            record_audit(
                db,
                "compliance.assessment.failed",
                "compliance_assessment",
                organization_id=account.organization_id,
                actor_user_id=user.id,
                metadata={
                    "aws_account_id": str(account.id),
                    "framework": payload.framework_key,
                    "error_code": "assessment_calculation_failed",
                },
            )
            db.commit()
            logger.error(
                "compliance.assessment.failed",
                extra={
                    "event_name": "compliance.assessment.failed",
                    "organization_id": str(account.organization_id),
                    "aws_account_id": str(account.id),
                    "error_code": "assessment_calculation_failed",
                },
            )
        raise


@router.get("/compliance/assessments", response_model=AssessmentListResponse)
def assessments(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    framework_key: str | None = None,
    framework_version: Annotated[str | None, Query(max_length=64)] = None,
    aws_account_id: uuid.UUID | None = None,
    assessment_status: ComplianceAssessmentStatus | None = None,
    control_status: ComplianceControlStatus | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    started_before: datetime | None = None,
    started_after: datetime | None = None,
    completed_before: datetime | None = None,
    completed_after: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AssessmentListResponse:
    _read_capability(db, user, organization_id)
    statement = select(ComplianceAssessment).where(
        ComplianceAssessment.organization_id == organization_id
    )
    if framework_key:
        statement = statement.join(ComplianceFramework).where(
            ComplianceFramework.key == framework_key
        )
    if framework_version:
        if framework_key is None:
            statement = statement.join(ComplianceFramework)
        statement = statement.where(ComplianceFramework.version == framework_version)
    if aws_account_id:
        statement = statement.where(ComplianceAssessment.aws_account_id == aws_account_id)
    if assessment_status:
        statement = statement.where(ComplianceAssessment.status == assessment_status)
    if control_status:
        statement = statement.where(
            ComplianceAssessment.id.in_(
                select(ComplianceAssessmentControl.assessment_id).where(
                    ComplianceAssessmentControl.status == control_status
                )
            )
        )
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if escaped:
            if framework_key is None and framework_version is None:
                statement = statement.join(ComplianceFramework)
            statement = statement.where(
                ComplianceFramework.name.ilike(f"%{escaped}%", escape="\\")
                | ComplianceFramework.key.ilike(f"%{escaped}%", escape="\\")
            )
    if started_before:
        statement = statement.where(ComplianceAssessment.started_at < started_before)
    if started_after:
        statement = statement.where(ComplianceAssessment.started_at > started_after)
    if completed_before:
        statement = statement.where(ComplianceAssessment.finished_at < completed_before)
    if completed_after:
        statement = statement.where(ComplianceAssessment.finished_at > completed_after)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        db.scalars(
            statement.order_by(ComplianceAssessment.created_at.desc(), ComplianceAssessment.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return AssessmentListResponse(
        items=[AssessmentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/compliance/assessments/{assessment_id}",
    response_model=AssessmentDetailResponse,
)
def assessment_detail(
    assessment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AssessmentDetailResponse:
    _read_capability(db, user, organization_id)
    item = db.scalar(
        select(ComplianceAssessment).where(
            ComplianceAssessment.id == assessment_id,
            ComplianceAssessment.organization_id == organization_id,
        )
    )
    if item is None:
        raise NotFoundError("assessment_not_found", "Compliance assessment was not found.")
    controls = list(
        db.scalars(
            select(ComplianceAssessmentControl)
            .where(ComplianceAssessmentControl.assessment_id == item.id)
            .order_by(ComplianceAssessmentControl.control_id)
        ).all()
    )
    response = AssessmentResponse.model_validate(item).model_dump()
    return AssessmentDetailResponse(
        **response,
        controls=[AssessmentControlResponse.model_validate(control) for control in controls],
    )


@router.get(
    "/compliance/assessments/{assessment_id}/controls/{snapshot_id}",
    response_model=AssessmentControlResponse,
)
def assessment_control_detail(
    assessment_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> AssessmentControlResponse:
    _read_capability(db, user, organization_id)
    snapshot = db.scalar(
        select(ComplianceAssessmentControl)
        .join(ComplianceAssessment)
        .where(
            ComplianceAssessmentControl.id == snapshot_id,
            ComplianceAssessmentControl.assessment_id == assessment_id,
            ComplianceAssessment.organization_id == organization_id,
        )
    )
    if snapshot is None:
        raise NotFoundError("assessment_control_not_found", "Assessment control was not found.")
    return AssessmentControlResponse.model_validate(snapshot)


@router.get("/compliance/controls/{control_id}", response_model=ControlResponse)
def control_detail(
    control_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> ControlResponse:
    _read_capability(db, user, organization_id)
    control = db.get(ComplianceControl, control_id)
    if control is None:
        raise NotFoundError("control_not_found", "Compliance control was not found.")
    return ControlResponse.model_validate(control)


@router.get(
    "/compliance/controls/{control_id}/rules",
    response_model=list[RuleControlMappingResponse],
)
def control_rules(
    control_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[RuleControlMappingResponse]:
    _read_capability(db, user, organization_id)
    if db.get(ComplianceControl, control_id) is None:
        raise NotFoundError("control_not_found", "Compliance control was not found.")
    mappings = db.scalars(
        select(RuleControlMapping)
        .where(RuleControlMapping.control_id == control_id)
        .order_by(
            RuleControlMapping.rule_key,
            RuleControlMapping.minimum_rule_version,
            RuleControlMapping.id,
        )
    ).all()
    return [RuleControlMappingResponse.model_validate(mapping) for mapping in mappings]


@router.get("/compliance/summary", response_model=ComplianceSummaryResponse)
def summary(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    framework_key: str | None = None,
    aws_account_id: uuid.UUID | None = None,
) -> ComplianceSummaryResponse:
    _read_capability(db, user, organization_id)
    statement = select(ComplianceAssessment).where(
        ComplianceAssessment.organization_id == organization_id
    )
    if framework_key:
        statement = statement.join(ComplianceFramework).where(
            ComplianceFramework.key == framework_key
        )
    if aws_account_id:
        statement = statement.where(ComplianceAssessment.aws_account_id == aws_account_id)
    assessments_subquery = statement.subquery()
    totals = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(assessments_subquery.c.controls_passed), 0),
            func.coalesce(func.sum(assessments_subquery.c.controls_failed), 0),
            func.coalesce(func.sum(assessments_subquery.c.controls_not_assessed), 0),
            func.coalesce(func.sum(assessments_subquery.c.controls_error), 0),
        ).select_from(assessments_subquery)
    ).one()
    return ComplianceSummaryResponse(
        assessments_total=totals[0],
        controls_passed=totals[1],
        controls_failed=totals[2],
        controls_not_assessed=totals[3],
        controls_error=totals[4],
    )


@router.get(
    "/compliance/controls/{control_id}/findings",
    response_model=ControlFindingResponse,
)
def control_findings(
    control_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    assessment_id: uuid.UUID | None = None,
    aws_account_id: uuid.UUID | None = None,
    severity: FindingSeverity | None = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
    service: Annotated[str | None, Query(max_length=32)] = None,
    rule_key: Annotated[str | None, Query(max_length=160)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ControlFindingResponse:
    _read_capability(db, user, organization_id)
    control = db.get(ComplianceControl, control_id)
    if control is None:
        raise NotFoundError("control_not_found", "Compliance control was not found.")
    status_value = None
    if assessment_id:
        snapshot = db.scalar(
            select(ComplianceAssessmentControl)
            .join(ComplianceAssessment)
            .where(
                ComplianceAssessmentControl.assessment_id == assessment_id,
                ComplianceAssessmentControl.control_id == control_id,
                ComplianceAssessment.organization_id == organization_id,
            )
        )
        if snapshot is None:
            raise NotFoundError("assessment_control_not_found", "Assessment control was not found.")
        status_value = snapshot.status
    rule_keys = list(
        db.scalars(
            select(RuleControlMapping.rule_key).where(RuleControlMapping.control_id == control_id)
        ).all()
    )
    finding_ids: list[uuid.UUID] = []
    total = 0
    if rule_keys:
        statement = select(Finding.id).where(
            Finding.organization_id == organization_id,
            Finding.rule_key.in_(rule_keys),
        )
        if aws_account_id:
            statement = statement.where(Finding.aws_account_id == aws_account_id)
        if severity:
            statement = statement.where(Finding.severity == severity)
        if rule_key:
            statement = statement.where(Finding.rule_key == rule_key)
        if service:
            normalized_service = service.strip().upper()
            if normalized_service:
                statement = statement.where(Finding.rule_key.startswith(f"{normalized_service}_"))
        if region:
            statement = statement.join(Asset, Finding.asset_id == Asset.id).where(
                Asset.region == region
            )
        if search:
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            if escaped:
                statement = statement.where(
                    Finding.rule_key.ilike(f"%{escaped}%", escape="\\")
                    | Finding.category.ilike(f"%{escaped}%", escape="\\")
                )
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        finding_ids = list(
            db.scalars(
                statement.order_by(Finding.last_seen_at.desc(), Finding.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
    return ControlFindingResponse(
        control=ControlResponse.model_validate(control),
        status=status_value,
        finding_ids=finding_ids,
        total=total,
        page=page,
        page_size=page_size,
    )
