from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base, TimestampMixin, TZAwareDateTime, utc_now
from app.models.enums import RemediationExecutionMode, RemediationStatus, enum_values

SENSITIVE_EVIDENCE_KEY = re.compile(
    r"(access.?key|secret|session.?token|credential|authorization|password)", re.I
)


def _contains_sensitive_evidence_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            SENSITIVE_EVIDENCE_KEY.search(str(key))
            or _contains_sensitive_evidence_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_evidence_key(item) for item in value)
    return False


class RemediationRequest(TimestampMixin, Base):
    """A proposal to remediate a specific finding. Version 1 only ever executes
    in MOCK_AUTOMATION mode; no real AWS mutation is performed by this model
    or its service. MANUAL and JIRA_DRAFT are informational execution modes;
    LIVE_AWS is reserved storage groundwork. None is auto-executed."""

    __tablename__ = "remediation_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_remediation_finding_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_count >= 0", name="remediation_attempt_count_nonnegative"),
        CheckConstraint("attempt_count <= 3", name="remediation_attempt_count_bounded"),
        CheckConstraint(
            "("
            "(status = 'pending_approval' AND approved_at IS NULL AND rejected_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL AND rejected_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'rejected' AND rejected_at IS NOT NULL AND approved_at IS NULL "
            "AND cancelled_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND rejected_at IS NULL AND executed_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'succeeded' AND approved_at IS NOT NULL AND executed_at IS NOT NULL "
            "AND rejected_at IS NULL AND cancelled_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'failed' AND approved_at IS NOT NULL AND failed_at IS NOT NULL "
            "AND rejected_at IS NULL AND cancelled_at IS NULL AND executed_at IS NULL)"
            ")",
            name="remediation_status_lifecycle",
        ),
        Index("ix_remediation_organization", "organization_id"),
        Index("ix_remediation_finding", "finding_id"),
        Index("ix_remediation_status", "status"),
        Index(
            "uq_remediation_tenant_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "uq_remediation_active_per_finding",
            "finding_id",
            unique=True,
            postgresql_where=text("status IN ('pending_approval', 'approved')"),
            sqlite_where=text("status IN ('pending_approval', 'approved')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action_key: Mapped[str] = mapped_column(String(160), nullable=False)
    action_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[RemediationStatus] = mapped_column(
        Enum(
            RemediationStatus,
            name="remediation_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=RemediationStatus.PENDING_APPROVAL,
        server_default=RemediationStatus.PENDING_APPROVAL.value,
        nullable=False,
    )
    execution_mode: Mapped[RemediationExecutionMode] = mapped_column(
        Enum(
            RemediationExecutionMode,
            name="remediation_execution_mode",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=RemediationExecutionMode.MOCK_AUTOMATION,
        server_default=RemediationExecutionMode.MOCK_AUTOMATION.value,
        nullable=False,
    )
    executor_key: Mapped[str | None] = mapped_column(String(64))
    target_region: Mapped[str | None] = mapped_column(String(64))
    target_resource_arn: Mapped[str | None] = mapped_column(String(2048))
    automation_eligible: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_steps_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("'[]'"), nullable=False
    )
    verification_steps_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("'[]'"), nullable=False
    )
    rollback_steps_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("'[]'"), nullable=False
    )
    preview_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    request_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    request_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    execution_lease_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dry_run: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    before_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    execution_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    precondition_evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    verification_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    aws_request_ids_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    requested_at: Mapped[datetime] = mapped_column(
        TZAwareDateTime(), default=utc_now, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    rejected_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    executed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())
    failed_at: Mapped[datetime | None] = mapped_column(TZAwareDateTime())

    @validates(
        "precondition_evidence_json",
        "verification_result_json",
        "aws_request_ids_json",
    )
    def reject_sensitive_execution_evidence(
        self, field: str, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None and _contains_sensitive_evidence_key(value):
            raise ValueError(f"{field} cannot contain credential-shaped fields")
        return value
