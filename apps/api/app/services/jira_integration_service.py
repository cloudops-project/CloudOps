from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.exceptions.errors import AppError, ConflictError, NotFoundError
from app.models import (
    AIRequest,
    AIRequestSource,
    AIResponse,
    Finding,
    JiraIntegration,
    JiraIssueLink,
    User,
)
from app.models.enums import AIRequestStatus, AISourceType, AITaskType, JiraIntegrationStatus
from app.repositories.data import Repository
from app.security import secret_box
from app.security.rbac import Capability
from app.services.common import now_utc, record_audit
from app.services.jira_client import JiraClient, JiraClientError, MockJiraClient, RealJiraClient
from app.services.organizations import OrganizationService

logger = logging.getLogger(__name__)


class JiraIntegrationService:
    """Organization-scoped CRUD and issue creation for Jira Cloud connections.

    Every operation refuses when Settings.jira_enabled is False, before any
    database read or write and before any HTTP call — the global switch is a
    fail-closed gate in front of tenant-scoped configuration, not merely a
    default. Jira is never on the scan/evaluation critical path: failures
    from this service are always caught and recorded by the caller (see
    create_issue_for_finding), never raised into rule evaluation or
    discovery.
    """

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        client: JiraClient | None = None,
    ) -> None:
        self.db = db
        self.repo = Repository(db)
        self.settings = settings or get_settings()
        self.client = client or self._default_client()

    def _default_client(self) -> JiraClient:
        if self.settings.app_env == "testing":
            return MockJiraClient()
        return RealJiraClient(
            connect_timeout_seconds=self.settings.jira_connect_timeout_seconds,
            read_timeout_seconds=self.settings.jira_read_timeout_seconds,
            max_retry_attempts=self.settings.jira_max_retry_attempts,
        )

    def _require_enabled(self) -> None:
        if not self.settings.jira_enabled:
            raise AppError(
                "jira_disabled",
                "Jira integration is disabled for this environment.",
                503,
            )

    def _encryption_key(self) -> bytes:
        return secret_box.load_key(self.settings.jira_token_encryption_key.get_secret_value())

    def create(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        base_url: str,
        project_key: str,
        default_issue_type: str,
        email: str,
        api_token: str,
    ) -> JiraIntegration:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_MANAGE
        )
        existing = self.repo.jira_integration_for_organization(organization_id)
        if existing is not None:
            raise ConflictError(
                "jira_integration_exists",
                "This organization already has an active Jira connection.",
            )
        encrypted_token = secret_box.encrypt(api_token, self._encryption_key())
        integration = JiraIntegration(
            organization_id=organization_id,
            base_url=base_url,
            project_key=project_key,
            default_issue_type=default_issue_type,
            email=email,
            api_token_encrypted=encrypted_token,
            created_by_user_id=actor.id,
        )
        self.db.add(integration)
        self.db.flush()
        self._audit("jira.integration.created", integration, actor.id)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "jira_integration_conflict", "The Jira connection could not be created."
            ) from exc
        self.db.refresh(integration)
        return integration

    def get(self, organization_id: uuid.UUID, actor: User) -> JiraIntegration:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_READ
        )
        integration = self.repo.jira_integration_for_organization(organization_id)
        if integration is None:
            raise NotFoundError(
                "jira_integration_not_found", "No Jira connection is configured."
            )
        return integration

    def update(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        base_url: str | None = None,
        project_key: str | None = None,
        default_issue_type: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        enabled: bool | None = None,
    ) -> JiraIntegration:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_MANAGE
        )
        integration = self.repo.jira_integration_for_organization_for_update(organization_id)
        if integration is None:
            raise NotFoundError(
                "jira_integration_not_found", "No Jira connection is configured."
            )
        if base_url is not None:
            integration.base_url = base_url
        if project_key is not None:
            integration.project_key = project_key
        if default_issue_type is not None:
            integration.default_issue_type = default_issue_type
        if email is not None:
            integration.email = email
        if api_token is not None:
            integration.api_token_encrypted = secret_box.encrypt(
                api_token, self._encryption_key()
            )
        if enabled is not None:
            integration.enabled = enabled
        if base_url is not None or api_token is not None or email is not None:
            integration.status = JiraIntegrationStatus.PENDING
            integration.failure_reason = None
            integration.last_validated_at = None
        self._audit("jira.integration.updated", integration, actor.id)
        self._commit(integration)
        return integration

    def test_connection(self, organization_id: uuid.UUID, actor: User) -> JiraIntegration:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_MANAGE
        )
        integration = self.repo.jira_integration_for_organization_for_update(organization_id)
        if integration is None:
            raise NotFoundError(
                "jira_integration_not_found", "No Jira connection is configured."
            )
        api_token = secret_box.decrypt(integration.api_token_encrypted, self._encryption_key())
        try:
            self.client.test_connection(
                base_url=integration.base_url, email=integration.email, api_token=api_token
            )
        except JiraClientError as exc:
            integration.status = JiraIntegrationStatus.FAILED
            integration.failure_reason = exc.code.value
            integration.last_validated_at = now_utc()
            self._audit(
                "jira.integration.validation_failed",
                integration,
                actor.id,
                extra={"failure_reason": exc.code.value},
            )
            self._commit(integration)
            return integration
        integration.status = JiraIntegrationStatus.CONNECTED
        integration.failure_reason = None
        integration.last_validated_at = now_utc()
        self._audit("jira.integration.validation_succeeded", integration, actor.id)
        self._commit(integration)
        return integration

    def disconnect(self, organization_id: uuid.UUID, actor: User) -> JiraIntegration:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_MANAGE
        )
        integration = self.repo.jira_integration_for_organization_for_update(organization_id)
        if integration is None:
            raise NotFoundError(
                "jira_integration_not_found", "No Jira connection is configured."
            )
        integration.status = JiraIntegrationStatus.DISCONNECTED
        integration.enabled = False
        integration.failure_reason = None
        self._audit("jira.integration.disconnected", integration, actor.id)
        self._commit(integration)
        return integration

    def get_issue_link(
        self, organization_id: uuid.UUID, idempotency_key: str, actor: User
    ) -> JiraIssueLink | None:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_READ
        )
        return self.repo.jira_issue_link_by_idempotency_key(organization_id, idempotency_key)

    def create_issue_for_finding(
        self,
        organization_id: uuid.UUID,
        finding_id: uuid.UUID,
        actor: User,
        *,
        idempotency_key: str,
        remediation_request_id: uuid.UUID | None = None,
    ) -> JiraIssueLink:
        """Create (or return the existing) Jira issue for a finding.

        This is called from an API route or platform job, never from the
        scan/evaluation pipeline itself. Callers on those pipelines must
        catch exceptions from this method and record a failed/retryable
        state rather than letting a Jira outage fail the scan.
        """
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_MANAGE
        )
        existing_link = self.repo.jira_issue_link_by_idempotency_key(
            organization_id, idempotency_key
        )
        if existing_link is not None:
            return existing_link

        integration = self.repo.jira_integration_for_organization(organization_id)
        if integration is None:
            raise NotFoundError(
                "jira_integration_not_found", "No Jira connection is configured."
            )
        if not integration.enabled or integration.status != JiraIntegrationStatus.CONNECTED:
            raise ConflictError(
                "jira_integration_not_ready",
                "The Jira connection is not enabled and connected.",
            )
        finding = self.db.scalar(
            select(Finding).where(
                Finding.id == finding_id, Finding.organization_id == organization_id
            )
        )
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")

        summary, description = self._issue_content(organization_id, finding)
        api_token = secret_box.decrypt(integration.api_token_encrypted, self._encryption_key())
        result = self.client.create_issue(
            base_url=integration.base_url,
            email=integration.email,
            api_token=api_token,
            project_key=integration.project_key,
            issue_type=integration.default_issue_type,
            summary=summary,
            description=description,
            labels=["cloudops", finding.severity.value],
        )
        link = JiraIssueLink(
            organization_id=organization_id,
            jira_integration_id=integration.id,
            finding_id=finding.id,
            remediation_request_id=remediation_request_id,
            idempotency_key=idempotency_key,
            issue_key=result.issue_key,
            issue_url=result.issue_url,
            created_by_user_id=actor.id,
        )
        self.db.add(link)
        self.db.flush()
        self._audit(
            "jira.issue.created",
            integration,
            actor.id,
            extra={"finding_id": str(finding.id), "issue_key": result.issue_key},
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            # A concurrent call already inserted the same idempotency key;
            # return that row rather than creating a second Jira issue.
            duplicate = self.repo.jira_issue_link_by_idempotency_key(
                organization_id, idempotency_key
            )
            if duplicate is not None:
                return duplicate
            raise ConflictError(
                "jira_issue_link_conflict", "The Jira issue link could not be recorded."
            ) from exc
        self.db.refresh(link)
        return link

    def issue_links_for_finding(
        self, organization_id: uuid.UUID, finding_id: uuid.UUID, actor: User
    ) -> list[JiraIssueLink]:
        self._require_enabled()
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.JIRA_READ
        )
        finding = self.db.scalar(
            select(Finding).where(
                Finding.id == finding_id,
                Finding.organization_id == organization_id,
            )
        )
        if finding is None:
            raise NotFoundError("finding_not_found", "Finding was not found.")
        return self.repo.jira_issue_links_for_finding(organization_id, finding_id)

    def _issue_content(
        self, organization_id: uuid.UUID, finding: Finding
    ) -> tuple[str, str]:
        """Prefer the persisted AITaskType.JIRA_DESCRIPTION draft for this
        finding when one has completed; otherwise fall back to a
        deterministic template built only from persisted evidence."""
        response = self.db.scalar(
            select(AIResponse)
            .join(AIRequest, AIRequest.id == AIResponse.request_id)
            .join(AIRequestSource, AIRequestSource.request_id == AIRequest.id)
            .where(
                AIRequest.organization_id == organization_id,
                AIRequest.task_type == AITaskType.JIRA_DESCRIPTION,
                AIRequest.status == AIRequestStatus.COMPLETED,
                AIRequestSource.source_type == AISourceType.FINDING,
                AIRequestSource.source_id == finding.id,
            )
            .order_by(AIRequest.created_at.desc())
            .limit(1)
        )
        summary = f"CloudOps finding: {finding.rule_key} ({finding.severity.value})"
        if response is not None:
            content = response.content_json
            title = content.get("title") if isinstance(content, dict) else None
            body = content.get("summary") if isinstance(content, dict) else None
            details = content.get("details") if isinstance(content, dict) else None
            lines = [str(body or "")]
            if isinstance(details, list):
                lines.extend(f"- {item}" for item in details)
            return (str(title) if title else summary, "\n".join(part for part in lines if part))
        description = (
            f"Rule: {finding.rule_key} (v{finding.rule_version})\n"
            f"Severity: {finding.severity.value}\n"
            f"Category: {finding.category}\n"
            f"Status: {finding.status.value}\n"
            "This is a deterministic draft; no AI draft was available."
        )
        return summary, description

    def _commit(self, integration: JiraIntegration) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "jira_integration_conflict", "The Jira connection update conflicts."
            ) from exc
        self.db.refresh(integration)

    def _audit(
        self,
        event_type: str,
        integration: JiraIntegration,
        actor_user_id: uuid.UUID,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {"jira_integration_id": str(integration.id)}
        if extra:
            metadata.update(extra)
        record_audit(
            self.db,
            event_type,
            "jira_integration",
            organization_id=integration.organization_id,
            actor_user_id=actor_user_id,
            resource_id=integration.id,
            metadata=metadata,
        )
