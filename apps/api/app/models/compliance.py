from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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

from app.db.base import Base, TimestampMixin
from app.models.enums import ComplianceAssessmentStatus, ComplianceControlStatus, enum_values


class ComplianceFramework(TimestampMixin, Base):
    __tablename__ = "compliance_frameworks"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_compliance_framework_key_version"),
        Index("ix_compliance_framework_enabled", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    official_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComplianceControl(TimestampMixin, Base):
    __tablename__ = "compliance_controls"
    __table_args__ = (
        UniqueConstraint("framework_id", "control_key", name="uq_compliance_control_key"),
        UniqueConstraint("id", "framework_id", name="uq_compliance_control_id_framework"),
        Index("ix_compliance_control_framework", "framework_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=False
    )
    control_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    section: Mapped[str | None] = mapped_column(String(200))
    parent_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("compliance_controls.id", ondelete="SET NULL")
    )


class RuleControlMapping(TimestampMixin, Base):
    __tablename__ = "rule_control_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["control_id", "framework_id"],
            ["compliance_controls.id", "compliance_controls.framework_id"],
            name="fk_rule_mapping_control_framework",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "rule_key",
            "minimum_rule_version",
            "maximum_rule_version",
            "control_id",
            name="uq_rule_control_version_range",
        ),
        CheckConstraint("minimum_rule_version > 0", name="rule_mapping_minimum_version_positive"),
        CheckConstraint(
            "maximum_rule_version IS NULL OR maximum_rule_version >= minimum_rule_version",
            name="rule_mapping_version_range_valid",
        ),
        Index("ix_rule_control_mapping_rule", "rule_key"),
        Index(
            "uq_rule_control_open_range",
            "rule_key",
            "minimum_rule_version",
            "control_id",
            unique=True,
            postgresql_where=text("maximum_rule_version IS NULL"),
            sqlite_where=text("maximum_rule_version IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    minimum_rule_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    maximum_rule_version: Mapped[int | None] = mapped_column(Integer)
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=False
    )
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    mapping_type: Mapped[str] = mapped_column(
        String(32), default="detective", server_default="detective", nullable=False
    )
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)


class ComplianceAssessment(TimestampMixin, Base):
    __tablename__ = "compliance_assessments"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_compliance_assessment_id_organization"),
        ForeignKeyConstraint(
            ["aws_account_id", "organization_id"],
            ["aws_accounts.id", "aws_accounts.organization_id"],
            name="fk_assessment_account_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evaluation_job_id", "aws_account_id", "organization_id"],
            [
                "evaluation_jobs.id",
                "evaluation_jobs.aws_account_id",
                "evaluation_jobs.organization_id",
            ],
            name="fk_assessment_evaluation_account_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "controls_total >= 0 AND controls_passed >= 0 AND controls_failed >= 0 "
            "AND controls_not_assessed >= 0 AND controls_error >= 0 AND findings_count >= 0",
            name="assessment_counts_nonnegative",
        ),
        CheckConstraint(
            "controls_total = controls_passed + controls_failed + controls_not_assessed "
            "+ controls_error",
            name="assessment_control_counts_match",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)",
            name="assessment_status_timestamps",
        ),
        Index("ix_assessment_organization", "organization_id"),
        Index("ix_assessment_account", "aws_account_id"),
        Index("ix_assessment_framework", "framework_id"),
        UniqueConstraint("id", "framework_id", name="uq_assessment_id_framework"),
        Index(
            "uq_active_assessment_account_framework",
            "aws_account_id",
            "framework_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    aws_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compliance_frameworks.id", ondelete="RESTRICT"), nullable=False
    )
    evaluation_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[ComplianceAssessmentStatus] = mapped_column(
        Enum(
            ComplianceAssessmentStatus,
            name="compliance_assessment_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        default=ComplianceAssessmentStatus.PENDING,
        server_default=ComplianceAssessmentStatus.PENDING.value,
        nullable=False,
    )
    controls_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    controls_passed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    controls_failed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    controls_not_assessed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    controls_error: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    findings_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(String(1000))


class ComplianceAssessmentControl(Base):
    __tablename__ = "compliance_assessment_controls"
    __table_args__ = (
        UniqueConstraint("assessment_id", "control_id", name="uq_assessment_control_snapshot"),
        CheckConstraint("findings_count >= 0", name="assessment_control_findings_nonnegative"),
        Index("ix_assessment_control_status", "status"),
        ForeignKeyConstraint(
            ["assessment_id", "framework_id"],
            ["compliance_assessments.id", "compliance_assessments.framework_id"],
            name="fk_assessment_control_assessment_framework",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["control_id", "framework_id"],
            ["compliance_controls.id", "compliance_controls.framework_id"],
            name="fk_assessment_control_control_framework",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[ComplianceControlStatus] = mapped_column(
        Enum(
            ComplianceControlStatus,
            name="compliance_control_status",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    findings_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvaluationRuleResult(TimestampMixin, Base):
    __tablename__ = "evaluation_rule_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evaluation_job_id", "aws_account_id", "organization_id"],
            [
                "evaluation_jobs.id",
                "evaluation_jobs.aws_account_id",
                "evaluation_jobs.organization_id",
            ],
            name="fk_rule_result_evaluation_account_organization",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "evaluation_job_id",
            "rule_key",
            "rule_version",
            name="uq_evaluation_rule_result",
        ),
        CheckConstraint("rule_version > 0", name="evaluation_rule_version_positive"),
        CheckConstraint(
            "passed_count >= 0 AND failed_count >= 0 AND not_applicable_count >= 0 "
            "AND error_count >= 0",
            name="evaluation_rule_counts_nonnegative",
        ),
        Index("ix_evaluation_rule_result_job", "evaluation_job_id"),
        Index("ix_evaluation_rule_result_rule", "rule_key", "rule_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_job_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    aws_account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    not_applicable_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
