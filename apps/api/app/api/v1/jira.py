from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AppSettings, CurrentUser, DbSession
from app.schemas.jira_integration import (
    JiraIntegrationCreate,
    JiraIntegrationResponse,
    JiraIntegrationUpdate,
    JiraIssueCreateRequest,
    JiraIssueLinkResponse,
)
from app.services.jira_integration_service import JiraIntegrationService

router = APIRouter()


@router.post(
    "/organizations/{organization_id}/jira",
    response_model=JiraIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_jira_integration(
    organization_id: uuid.UUID,
    payload: JiraIntegrationCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> JiraIntegrationResponse:
    integration = JiraIntegrationService(db, settings).create(
        organization_id,
        user,
        base_url=payload.base_url,
        project_key=payload.project_key,
        default_issue_type=payload.default_issue_type,
        email=payload.email,
        api_token=payload.api_token,
    )
    return JiraIntegrationResponse.model_validate(integration)


@router.get(
    "/organizations/{organization_id}/jira",
    response_model=JiraIntegrationResponse,
)
def get_jira_integration(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> JiraIntegrationResponse:
    integration = JiraIntegrationService(db, settings).get(organization_id, user)
    return JiraIntegrationResponse.model_validate(integration)


@router.patch(
    "/organizations/{organization_id}/jira",
    response_model=JiraIntegrationResponse,
)
def update_jira_integration(
    organization_id: uuid.UUID,
    payload: JiraIntegrationUpdate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> JiraIntegrationResponse:
    integration = JiraIntegrationService(db, settings).update(
        organization_id,
        user,
        base_url=payload.base_url,
        project_key=payload.project_key,
        default_issue_type=payload.default_issue_type,
        email=payload.email,
        api_token=payload.api_token,
        enabled=payload.enabled,
    )
    return JiraIntegrationResponse.model_validate(integration)


@router.post(
    "/organizations/{organization_id}/jira/test",
    response_model=JiraIntegrationResponse,
)
def test_jira_integration(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> JiraIntegrationResponse:
    integration = JiraIntegrationService(db, settings).test_connection(organization_id, user)
    return JiraIntegrationResponse.model_validate(integration)


@router.delete(
    "/organizations/{organization_id}/jira",
    response_model=JiraIntegrationResponse,
)
def disconnect_jira_integration(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> JiraIntegrationResponse:
    integration = JiraIntegrationService(db, settings).disconnect(organization_id, user)
    return JiraIntegrationResponse.model_validate(integration)


@router.post(
    "/organizations/{organization_id}/findings/{finding_id}/jira-issues",
    response_model=JiraIssueLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_jira_issue_for_finding(
    organization_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: JiraIssueCreateRequest,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> JiraIssueLinkResponse:
    link = JiraIntegrationService(db, settings).create_issue_for_finding(
        organization_id,
        finding_id,
        user,
        idempotency_key=payload.idempotency_key,
        remediation_request_id=payload.remediation_request_id,
    )
    return JiraIssueLinkResponse.model_validate(link)


@router.get(
    "/organizations/{organization_id}/findings/{finding_id}/jira-issues",
    response_model=list[JiraIssueLinkResponse],
)
def list_jira_issues_for_finding(
    organization_id: uuid.UUID,
    finding_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> list[JiraIssueLinkResponse]:
    links = JiraIntegrationService(db, settings).issue_links_for_finding(
        organization_id, finding_id, user
    )
    return [JiraIssueLinkResponse.model_validate(link) for link in links]
