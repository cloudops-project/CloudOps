from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import JiraIntegrationStatus, enum_values


class JiraIntegration(TimestampMixin, Base):
    """A single organization's connection to a Jira Cloud site.

    Scoped per-organization exactly like AWSAccount, not a single global
    environment setting. The API token is stored only in encrypted form
    (app.security.secret_box); this model never exposes plaintext. The
    global Settings.jira_enabled kill switch is enforced by the service
    layer, not here — this table can exist and be read only when that
    switch is on.
    """

    __tablename__ = "jira_integrations"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_jira_integration_id_organization"),
        Index("ix_jira_integration_organization", "organization_id"),
        Index(
            "uq_jira_integration_active_per_organization",
            "organization_id",
            unique=True,
            postgresql_where=text("status != 'disconnected'"),
            sqlite_where=text("status != 'disconnected'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    default_issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    api_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    status: Mapped[JiraIntegrationStatus] = mapped_column(
        Enum(
            JiraIntegrationStatus,
            name="jira_integration_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=JiraIntegrationStatus.PENDING,
        server_default=JiraIntegrationStatus.PENDING.value,
        nullable=False,
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class JiraIssueLink(TimestampMixin, Base):
    """Idempotent record of a Jira issue created for a finding or remediation
    request. The unique idempotency_key per organization prevents duplicate
    ticket creation when create_issue_for_finding is called more than once
    for the same finding (e.g. retried job, duplicate API call)."""

    __tablename__ = "jira_issue_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["jira_integration_id", "organization_id"],
            ["jira_integrations.id", "jira_integrations.organization_id"],
            name="fk_jira_issue_link_integration_organization",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_jira_issue_link_tenant_idempotency"
        ),
        Index("ix_jira_issue_link_organization", "organization_id"),
        Index("ix_jira_issue_link_finding", "finding_id"),
        Index("ix_jira_issue_link_remediation_request", "remediation_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    jira_integration_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("findings.id", ondelete="SET NULL")
    )
    remediation_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("remediation_requests.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
