from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utc_now
from app.models.enums import AssetType, enum_values


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("aws_account_id", "asset_type", "resource_id", name="uq_asset_identity"),
        UniqueConstraint(
            "id",
            "aws_account_id",
            "organization_id",
            name="uq_asset_id_account_organization",
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="asset_seen_order"),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_asset_account_organization",
            ondelete="CASCADE",
        ),
        Index("ix_asset_organization", "organization_id"),
        Index("ix_asset_aws_account", "aws_account_id"),
        Index("ix_asset_type", "asset_type"),
        Index("ix_asset_region", "region"),
        Index("ix_asset_status", "status"),
        Index("ix_asset_is_active", "is_active"),
        Index("ix_asset_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(
            AssetType,
            name="asset_type",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    resource_id: Mapped[str] = mapped_column(String(512), nullable=False)
    arn: Mapped[str | None] = mapped_column(String(2048))
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
