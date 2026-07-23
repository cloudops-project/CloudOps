from __future__ import annotations

import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, status

from app.dependencies.auth import CurrentUser, DbSession
from app.exceptions.errors import NotFoundError
from app.models import EvaluationJob, Finding
from app.models.enums import FindingSeverity, FindingStatus
from app.repositories.findings import EvaluationJobRepository, FindingRepository
from app.schemas.findings import (
    EvaluationJobListResponse,
    EvaluationJobResponse,
    EvaluationRequest,
    FindingListResponse,
    FindingResponse,
    FindingSummaryItem,
    FindingSummaryResponse,
    FindingSuppressRequest,
    RuleResponse,
)
from app.security.rbac import Capability
from app.security_rules import default_registry
from app.security_rules.base import SecurityRule
from app.security_rules.results import sanitize_evidence
from app.services.evaluations import EvaluationService
from app.services.organizations import OrganizationService

router = APIRouter()


def _rule_response(rule: SecurityRule) -> RuleResponse:
    return RuleResponse(
        key=rule.key,
        version=rule.version,
        name=rule.name,
        description=rule.description,
        service=rule.service,
        asset_type=rule.asset_type,
        category=rule.category,
        severity=rule.severity,
        remediation=rule.remediation,
        references=list(rule.references),
        enabled_by_default=rule.enabled_by_default,
    )


def _finding_response(finding: Finding) -> FindingResponse:
    return FindingResponse(
        id=finding.id,
        organization_id=finding.organization_id,
        aws_account_id=finding.aws_account_id,
        asset_id=finding.asset_id,
        rule_key=finding.rule_key,
        rule_version=finding.rule_version,
        severity=finding.severity,
        category=finding.category,
        status=finding.status,
        evidence=cast(dict[str, Any], sanitize_evidence(finding.evidence_json)),
        first_seen_at=finding.first_seen_at,
        last_seen_at=finding.last_seen_at,
        resolved_at=finding.resolved_at,
        suppressed_at=finding.suppressed_at,
        suppressed_until=finding.suppressed_until,
        suppression_reason=finding.suppression_reason,
        suppressed_by_user_id=finding.suppressed_by_user_id,
        last_evaluation_id=finding.last_evaluation_id,
        lifecycle_version=finding.lifecycle_version,
        created_at=finding.created_at,
        updated_at=finding.updated_at,
    )


@router.get("/rules", response_model=list[RuleResponse])
def list_rules(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> list[RuleResponse]:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.RULES_READ)
    return [_rule_response(rule) for rule in default_registry.all()]


@router.get("/rules/{rule_key}", response_model=RuleResponse)
def get_rule(
    rule_key: str,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> RuleResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.RULES_READ)
    rule = default_registry.get(rule_key)
    if rule is None:
        raise NotFoundError("rule_not_found", "Rule was not found.")
    return _rule_response(rule)


@router.post(
    "/aws/accounts/{account_id}/evaluate",
    response_model=EvaluationJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_evaluation(
    account_id: uuid.UUID,
    payload: EvaluationRequest,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationJob:
    return EvaluationService(db).start(account_id, user, discovery_job_id=payload.discovery_job_id)


@router.get("/evaluations", response_model=EvaluationJobListResponse)
def list_evaluations(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EvaluationJobListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.FINDINGS_READ)
    items, total = EvaluationJobRepository(db).list(organization_id, page, page_size)
    return EvaluationJobListResponse(
        items=[EvaluationJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationJobResponse)
def get_evaluation(
    evaluation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> EvaluationJob:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.FINDINGS_READ)
    job = EvaluationJobRepository(db).get(organization_id, evaluation_id)
    if job is None:
        raise NotFoundError("evaluation_not_found", "Evaluation was not found.")
    return job


@router.get("/findings", response_model=FindingListResponse)
def list_findings(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
    aws_account_id: uuid.UUID | None = None,
    severity: FindingSeverity | None = None,
    finding_status: Annotated[FindingStatus | None, Query(alias="status")] = None,
    rule_key: Annotated[str | None, Query(max_length=160)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FindingListResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.FINDINGS_READ)
    items, total = FindingRepository(db).list(
        organization_id,
        account_id=aws_account_id,
        severity=severity,
        status=finding_status,
        rule_key=rule_key,
        search=search,
        page=page,
        page_size=page_size,
    )
    return FindingListResponse(
        items=[_finding_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/findings/summary", response_model=FindingSummaryResponse)
def findings_summary(
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FindingSummaryResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.FINDINGS_READ)
    items = [
        FindingSummaryItem(severity=severity, status=status_value, count=count)
        for severity, status_value, count in FindingRepository(db).summary(organization_id)
    ]
    return FindingSummaryResponse(total=sum(item.count for item in items), items=items)


@router.get("/findings/{finding_id}", response_model=FindingResponse)
def get_finding(
    finding_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FindingResponse:
    OrganizationService(db).require_capability(organization_id, user.id, Capability.FINDINGS_READ)
    finding = FindingRepository(db).get(organization_id, finding_id)
    if finding is None:
        raise NotFoundError("finding_not_found", "Finding was not found.")
    return _finding_response(finding)


@router.post("/findings/{finding_id}/suppress", response_model=FindingResponse)
def suppress_finding(
    finding_id: uuid.UUID,
    payload: FindingSuppressRequest,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FindingResponse:
    finding = EvaluationService(db).suppress(
        organization_id,
        finding_id,
        user,
        payload.reason,
        payload.suppressed_until,
    )
    return _finding_response(finding)


@router.post("/findings/{finding_id}/unsuppress", response_model=FindingResponse)
def unsuppress_finding(
    finding_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    organization_id: Annotated[uuid.UUID, Query()],
) -> FindingResponse:
    return _finding_response(EvaluationService(db).unsuppress(organization_id, finding_id, user))
