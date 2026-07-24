from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utc_now
from app.models.enums import AIRequestStatus, AISourceType, AITaskType, enum_values


class AIPromptTemplate(Base):
    __tablename__ = "ai_prompt_templates"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_ai_prompt_template_key_version"),
        CheckConstraint("version > 0", name="ai_prompt_template_version_positive"),
        CheckConstraint("schema_version > 0", name="ai_prompt_template_schema_positive"),
        Index(
            "uq_ai_prompt_template_active_task",
            "task_type",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[AITaskType] = mapped_column(
        Enum(
            AITaskType,
            name="ai_task_type",
            native_enum=False,
            create_constraint=True,
            length=40,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AIRequest(TimestampMixin, Base):
    __tablename__ = "ai_requests"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_request_id_organization"),
        UniqueConstraint(
            "organization_id",
            "requested_by_user_id",
            "idempotency_key",
            name="uq_ai_request_idempotency",
        ),
        CheckConstraint("prompt_version > 0", name="ai_request_prompt_version_positive"),
        CheckConstraint(
            "(status IN ('pending', 'running') AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND finished_at IS NOT NULL)",
            name="ai_request_terminal_timestamp",
        ),
        Index("ix_ai_request_organization", "organization_id"),
        Index("ix_ai_request_status", "status"),
        Index("ix_ai_request_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    task_type: Mapped[AITaskType] = mapped_column(
        Enum(
            AITaskType,
            name="ai_request_task_type",
            native_enum=False,
            create_constraint=True,
            length=40,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    status: Mapped[AIRequestStatus] = mapped_column(
        Enum(
            AIRequestStatus,
            name="ai_request_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=enum_values,
        ),
        default=AIRequestStatus.PENDING,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), default="mock", nullable=False)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIRequestSource(Base):
    __tablename__ = "ai_request_sources"
    __table_args__ = (
        UniqueConstraint("request_id", "source_type", "source_id", name="uq_ai_request_source"),
        CheckConstraint("source_version > 0", name="ai_source_version_positive"),
        ForeignKeyConstraint(
            ["request_id", "organization_id"],
            ["ai_requests.id", "ai_requests.organization_id"],
            name="fk_ai_source_request_organization",
            ondelete="CASCADE",
        ),
        Index("ix_ai_source_lookup", "organization_id", "source_type", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_type: Mapped[AISourceType] = mapped_column(
        Enum(
            AISourceType,
            name="ai_source_type",
            native_enum=False,
            create_constraint=True,
            length=40,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AIResponse(Base):
    __tablename__ = "ai_responses"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_ai_response_request"),
        ForeignKeyConstraint(
            ["request_id", "organization_id"],
            ["ai_requests.id", "ai_requests.organization_id"],
            name="fk_ai_response_request_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint("schema_version > 0", name="ai_response_schema_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AIUsageWindow(Base):
    __tablename__ = "ai_usage_windows"
    __table_args__ = (
        UniqueConstraint("organization_id", "window_start", name="uq_ai_usage_window"),
        CheckConstraint(
            "request_count >= 0 AND token_count >= 0", name="ai_usage_counts_nonnegative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
