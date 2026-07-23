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
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utc_now
from app.models.enums import FindingSeverity, FindingStatus, enum_values


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "aws_account_id",
            "organization_id",
            name="uq_finding_id_account_organization",
        ),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_finding_account_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["asset_id", "aws_account_id", "organization_id"],
            ["assets.id", "assets.aws_account_id", "assets.organization_id"],
            name="fk_finding_asset_account_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint("rule_version > 0", name="finding_rule_version_positive"),
        CheckConstraint("lifecycle_version >= 0", name="finding_lifecycle_version_nonnegative"),
        CheckConstraint("last_seen_at >= first_seen_at", name="finding_seen_order"),
        CheckConstraint(
            "("
            "(status = 'open' AND resolved_at IS NULL AND suppressed_at IS NULL "
            "AND suppressed_by_user_id IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND suppressed_at IS NULL "
            "AND suppressed_by_user_id IS NULL) OR "
            "(status = 'suppressed' AND resolved_at IS NULL AND suppressed_at IS NOT NULL "
            "AND suppression_reason IS NOT NULL AND suppression_reason <> '' "
            "AND suppressed_by_user_id IS NOT NULL)"
            ")",
            name="finding_status_lifecycle",
        ),
        Index("ix_finding_organization", "organization_id"),
        Index("ix_finding_account", "aws_account_id"),
        Index("ix_finding_asset", "asset_id"),
        Index("ix_finding_rule", "rule_key"),
        Index("ix_finding_status", "status"),
        Index("ix_finding_severity", "severity"),
        Index("ix_finding_last_seen", "last_seen_at"),
        Index(
            "uq_finding_asset_rule",
            "asset_id",
            "rule_key",
            unique=True,
            postgresql_where=text("asset_id IS NOT NULL"),
            sqlite_where=text("asset_id IS NOT NULL"),
        ),
        Index(
            "uq_finding_account_rule",
            "aws_account_id",
            "rule_key",
            unique=True,
            postgresql_where=text("asset_id IS NULL"),
            sqlite_where=text("asset_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(
            FindingSeverity,
            name="finding_severity",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[FindingStatus] = mapped_column(
        Enum(
            FindingStatus,
            name="finding_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=FindingStatus.OPEN,
        server_default=FindingStatus.OPEN.value,
        nullable=False,
    )
    evidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppression_reason: Mapped[str | None] = mapped_column(String(1000))
    suppressed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    last_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
