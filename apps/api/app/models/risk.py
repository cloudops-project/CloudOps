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
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utc_now
from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingStatus,
    RiskAssessmentStatus,
    RiskCriticality,
    RiskEnvironment,
    RiskPriority,
    enum_values,
)


class RiskScoringPolicy(Base):
    __tablename__ = "risk_scoring_policies"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_risk_policy_key_version"),
        CheckConstraint("version > 0", name="risk_policy_version_positive"),
        Index("ix_risk_policy_active", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    bands_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AssetRiskContext(TimestampMixin, Base):
    __tablename__ = "asset_risk_contexts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_risk_context_account_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["asset_id", "aws_account_id", "organization_id"],
            ["assets.id", "assets.aws_account_id", "assets.organization_id"],
            name="fk_risk_context_asset_account_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint("version > 0", name="risk_context_version_positive"),
        Index("ix_risk_context_organization", "organization_id"),
        Index("ix_risk_context_account", "aws_account_id"),
        Index(
            "uq_risk_context_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("asset_id IS NOT NULL"),
            sqlite_where=text("asset_id IS NOT NULL"),
        ),
        Index(
            "uq_risk_context_account_default",
            "aws_account_id",
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
    criticality: Mapped[RiskCriticality] = mapped_column(
        Enum(
            RiskCriticality,
            name="risk_criticality",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=RiskCriticality.UNKNOWN,
        server_default=RiskCriticality.UNKNOWN.value,
        nullable=False,
    )
    environment: Mapped[RiskEnvironment] = mapped_column(
        Enum(
            RiskEnvironment,
            name="risk_environment",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=RiskEnvironment.UNKNOWN,
        server_default=RiskEnvironment.UNKNOWN.value,
        nullable=False,
    )
    business_impact: Mapped[BusinessImpact] = mapped_column(
        Enum(
            BusinessImpact,
            name="business_impact",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=BusinessImpact.UNKNOWN,
        server_default=BusinessImpact.UNKNOWN.value,
        nullable=False,
    )
    data_sensitivity: Mapped[DataSensitivity] = mapped_column(
        Enum(
            DataSensitivity,
            name="data_sensitivity",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=DataSensitivity.UNKNOWN,
        server_default=DataSensitivity.UNKNOWN.value,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class RiskAssessment(TimestampMixin, Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_risk_assessment_id_organization"),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_risk_assessment_account_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "findings_total >= 0 AND critical_count >= 0 AND high_count >= 0 "
            "AND medium_count >= 0 AND low_count >= 0 AND informational_count >= 0 "
            "AND accounts_scored >= 0",
            name="risk_assessment_counts_nonnegative",
        ),
        CheckConstraint(
            "findings_total = critical_count + high_count + medium_count + low_count "
            "+ informational_count",
            name="risk_assessment_counts_match",
        ),
        CheckConstraint(
            "aggregate_score IS NULL OR (aggregate_score >= 0 AND aggregate_score <= 100)",
            name="risk_assessment_score_range",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)",
            name="risk_assessment_status_timestamps",
        ),
        Index("ix_risk_assessment_organization", "organization_id"),
        Index("ix_risk_assessment_account", "aws_account_id"),
        Index("ix_risk_assessment_status", "status"),
        Index(
            "uq_active_risk_assessment_account",
            "organization_id",
            "aws_account_id",
            "policy_id",
            unique=True,
            postgresql_where=text(
                "aws_account_id IS NOT NULL AND status IN ('pending', 'running')"
            ),
            sqlite_where=text("aws_account_id IS NOT NULL AND status IN ('pending', 'running')"),
        ),
        Index(
            "uq_active_risk_assessment_organization",
            "organization_id",
            "policy_id",
            unique=True,
            postgresql_where=text("aws_account_id IS NULL AND status IN ('pending', 'running')"),
            sqlite_where=text("aws_account_id IS NULL AND status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("risk_scoring_policies.id", ondelete="RESTRICT"), nullable=False
    )
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[RiskAssessmentStatus] = mapped_column(
        Enum(
            RiskAssessmentStatus,
            name="risk_assessment_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=RiskAssessmentStatus.PENDING,
        server_default=RiskAssessmentStatus.PENDING.value,
        nullable=False,
    )
    started_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    findings_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    critical_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    high_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    medium_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    low_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    informational_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    accounts_scored: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    aggregate_score: Mapped[int | None] = mapped_column(Integer)
    aggregate_priority: Mapped[RiskPriority | None] = mapped_column(
        Enum(
            RiskPriority,
            name="risk_priority",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        )
    )
    error_code: Mapped[str | None] = mapped_column(String(100))


class FindingRiskSnapshot(Base):
    __tablename__ = "finding_risk_snapshots"
    __table_args__ = (
        UniqueConstraint("assessment_id", "finding_id", name="uq_finding_risk_snapshot"),
        ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_finding_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_finding_risk_finding_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("policy_version > 0", name="finding_risk_policy_version_positive"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="finding_risk_score_range"),
        CheckConstraint(
            "severity_points BETWEEN 0 AND 30 AND exposure_points BETWEEN 0 AND 15 "
            "AND exploitability_points BETWEEN 0 AND 10 AND privilege_points BETWEEN 0 AND 10 "
            "AND asset_criticality_points BETWEEN 0 AND 10 "
            "AND environment_points BETWEEN 0 AND 5 "
            "AND business_impact_points BETWEEN 0 AND 10 "
            "AND data_sensitivity_points BETWEEN 0 AND 5 "
            "AND age_points BETWEEN 0 AND 5",
            name="finding_risk_component_ranges",
        ),
        CheckConstraint(
            "compensating_adjustment BETWEEN -15 AND 0",
            name="finding_risk_adjustment_range",
        ),
        Index("ix_finding_risk_organization", "organization_id"),
        Index("ix_finding_risk_account", "aws_account_id"),
        Index("ix_finding_risk_finding", "finding_id"),
        Index("ix_finding_risk_score", "risk_score"),
        Index("ix_finding_risk_priority", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source_finding_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_finding_status: Mapped[FindingStatus] = mapped_column(
        Enum(
            FindingStatus,
            name="risk_source_finding_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    policy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[RiskPriority] = mapped_column(
        Enum(
            RiskPriority,
            name="finding_risk_priority",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    severity_points: Mapped[int] = mapped_column(Integer, nullable=False)
    exposure_points: Mapped[int] = mapped_column(Integer, nullable=False)
    exploitability_points: Mapped[int] = mapped_column(Integer, nullable=False)
    privilege_points: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_criticality_points: Mapped[int] = mapped_column(Integer, nullable=False)
    environment_points: Mapped[int] = mapped_column(Integer, nullable=False)
    business_impact_points: Mapped[int] = mapped_column(Integer, nullable=False)
    data_sensitivity_points: Mapped[int] = mapped_column(Integer, nullable=False)
    age_points: Mapped[int] = mapped_column(Integer, nullable=False)
    compensating_adjustment: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    component_codes_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    unknown_inputs_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AccountRiskSnapshot(Base):
    __tablename__ = "account_risk_snapshots"
    __table_args__ = (
        UniqueConstraint("assessment_id", "aws_account_id", name="uq_account_risk_snapshot"),
        ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_account_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_account_risk_account_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "risk_score BETWEEN 0 AND 100 AND highest_finding_score BETWEEN 0 AND 100 "
            "AND top_ten_mean BETWEEN 0 AND 100 AND all_findings_mean BETWEEN 0 AND 100 "
            "AND findings_total >= 0",
            name="account_risk_ranges",
        ),
        Index("ix_account_risk_organization", "organization_id"),
        Index("ix_account_risk_account", "aws_account_id"),
        Index("ix_account_risk_score", "risk_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[RiskPriority] = mapped_column(
        Enum(
            RiskPriority,
            name="account_risk_priority",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    highest_finding_score: Mapped[int] = mapped_column(Integer, nullable=False)
    top_ten_mean: Mapped[int] = mapped_column(Integer, nullable=False)
    all_findings_mean: Mapped[int] = mapped_column(Integer, nullable=False)
    findings_total: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class OrganizationRiskSnapshot(Base):
    __tablename__ = "organization_risk_snapshots"
    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_organization_risk_snapshot"),
        ForeignKeyConstraint(
            ["assessment_id", "organization_id"],
            ["risk_assessments.id", "risk_assessments.organization_id"],
            name="fk_organization_risk_assessment_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "risk_score BETWEEN 0 AND 100 AND highest_account_score BETWEEN 0 AND 100 "
            "AND mean_account_score BETWEEN 0 AND 100 AND accounts_total >= 0",
            name="organization_risk_ranges",
        ),
        Index("ix_organization_risk_organization", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    evaluation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[RiskPriority] = mapped_column(
        Enum(
            RiskPriority,
            name="organization_risk_priority",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    highest_account_score: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_account_score: Mapped[int] = mapped_column(Integer, nullable=False)
    accounts_total: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class CompensatingControl(TimestampMixin, Base):
    __tablename__ = "compensating_controls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "aws_account_id", "organization_id"],
            ["findings.id", "findings.aws_account_id", "findings.organization_id"],
            name="fk_compensating_control_finding_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "score_adjustment BETWEEN -15 AND -1",
            name="compensating_control_adjustment_range",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="compensating_control_expiry_order",
        ),
        Index("ix_compensating_control_organization", "organization_id"),
        Index("ix_compensating_control_finding", "finding_id"),
        Index(
            "uq_active_compensating_control_finding",
            "finding_id",
            unique=True,
            postgresql_where=text("active"),
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    score_adjustment: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
