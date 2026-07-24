from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.exceptions.errors import AppError, ConflictError, NotFoundError
from app.models import (
    AIPromptTemplate,
    AIRequest,
    AIRequestSource,
    AIResponse,
    AIUsageWindow,
    ComplianceAssessment,
    Finding,
    RiskAssessment,
)
from app.models.enums import AIRequestStatus, AISourceType
from app.schemas.ai import AIContent, AIGenerateRequest, AIRequestResponse
from app.services.ai_provider import AIProvider, MockAIProvider
from app.services.ai_safety import canonical_json, sanitize
from app.services.common import record_audit

logger = logging.getLogger(__name__)


class AIService:
    MAX_REQUESTS_PER_HOUR = 100

    def __init__(self, db: Session, provider: AIProvider | None = None) -> None:
        self.db = db
        self.provider = provider or MockAIProvider()

    def generate(self, payload: AIGenerateRequest, user_id: uuid.UUID) -> AIRequestResponse:
        existing = self.db.scalar(
            select(AIRequest).where(
                AIRequest.organization_id == payload.organization_id,
                AIRequest.requested_by_user_id == user_id,
                AIRequest.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return self.response(existing)
        template = self.db.scalar(
            select(AIPromptTemplate).where(
                AIPromptTemplate.task_type == payload.task_type,
                AIPromptTemplate.active.is_(True),
            )
        )
        if template is None:
            raise NotFoundError("ai_prompt_not_found", "AI prompt template was not found.")
        context, source_rows = self._build_context(payload)
        context_hash = hashlib.sha256(canonical_json(context).encode()).hexdigest()
        now = datetime.now(UTC)
        window_start = now.replace(minute=0, second=0, microsecond=0)
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"ai-quota:{payload.organization_id}:{window_start.isoformat()}"},
            )
            existing = self.db.scalar(
                select(AIRequest).where(
                    AIRequest.organization_id == payload.organization_id,
                    AIRequest.requested_by_user_id == user_id,
                    AIRequest.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return self.response(existing)
        usage = self.db.scalar(
            select(AIUsageWindow)
            .where(
                AIUsageWindow.organization_id == payload.organization_id,
                AIUsageWindow.window_start == window_start,
            )
            .with_for_update()
        )
        if usage is None:
            usage = AIUsageWindow(
                organization_id=payload.organization_id, window_start=window_start
            )
            self.db.add(usage)
            self.db.flush()
        if usage.request_count >= self.MAX_REQUESTS_PER_HOUR:
            raise ConflictError("ai_quota_exceeded", "The organization AI quota is exhausted.")
        request = AIRequest(
            organization_id=payload.organization_id,
            requested_by_user_id=user_id,
            task_type=payload.task_type,
            status=AIRequestStatus.RUNNING,
            idempotency_key=payload.idempotency_key,
            provider_key=self.provider.key,
            prompt_key=template.key,
            prompt_version=template.version,
            context_hash=context_hash,
        )
        self.db.add(request)
        self.db.flush()
        for source in source_rows:
            self.db.add(
                AIRequestSource(
                    request_id=request.id, organization_id=payload.organization_id, **source
                )
            )
        usage.request_count += 1
        record_audit(
            self.db,
            "ai.request.started",
            "ai_request",
            organization_id=payload.organization_id,
            actor_user_id=user_id,
            resource_id=request.id,
            metadata={"task_type": payload.task_type.value, "provider_key": self.provider.key},
        )
        logger.info(
            "ai.request.started",
            extra={
                "event_name": "ai.request.started",
                "organization_id": str(payload.organization_id),
                "request_id": str(request.id),
                "task_type": payload.task_type.value,
                "provider_key": self.provider.key,
            },
        )
        try:
            content = self.provider.generate(payload.task_type, context)
        except Exception:
            request.status = AIRequestStatus.FAILED
            request.error_code = "provider_failed"
            request.finished_at = now
            record_audit(
                self.db,
                "ai.request.failed",
                "ai_request",
                organization_id=payload.organization_id,
                actor_user_id=user_id,
                resource_id=request.id,
                metadata={"task_type": payload.task_type.value, "error_code": "provider_failed"},
            )
            self.db.commit()
            logger.error(
                "ai.request.failed",
                extra={
                    "event_name": "ai.request.failed",
                    "organization_id": str(payload.organization_id),
                    "request_id": str(request.id),
                    "task_type": payload.task_type.value,
                    "error_code": "provider_failed",
                },
            )
            raise AppError(
                "ai_provider_failed", "The AI draft could not be generated safely.", 502
            ) from None
        try:
            safe_content = AIContent.model_validate(sanitize(content.model_dump()))
            output = canonical_json(safe_content.model_dump())
            self.db.add(
                AIResponse(
                    request_id=request.id,
                    organization_id=payload.organization_id,
                    content_json=safe_content.model_dump(mode="json"),
                    schema_version=template.schema_version,
                    output_hash=hashlib.sha256(output.encode()).hexdigest(),
                )
            )
            usage.token_count += max(1, len(output) // 4)
            request.status = AIRequestStatus.COMPLETED
            request.finished_at = now
            record_audit(
                self.db,
                "ai.request.completed",
                "ai_request",
                organization_id=payload.organization_id,
                actor_user_id=user_id,
                resource_id=request.id,
                metadata={"task_type": payload.task_type.value, "provider_key": self.provider.key},
            )
            self.db.commit()
            logger.info(
                "ai.request.completed",
                extra={
                    "event_name": "ai.request.completed",
                    "organization_id": str(payload.organization_id),
                    "request_id": str(request.id),
                    "task_type": payload.task_type.value,
                    "provider_key": self.provider.key,
                },
            )
        except Exception:
            self.db.rollback()
            raise
        return self.response(request)

    def response(self, request: AIRequest) -> AIRequestResponse:
        response = self.db.scalar(select(AIResponse).where(AIResponse.request_id == request.id))
        data = AIRequestResponse.model_validate(request).model_dump()
        data["content"] = response.content_json if response else None
        return AIRequestResponse.model_validate(data)

    def _build_context(
        self, payload: AIGenerateRequest
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sources: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        for source in payload.sources:
            if source.source_type == AISourceType.FINDING:
                finding = self.db.scalar(
                    select(Finding).where(
                        Finding.id == source.source_id,
                        Finding.organization_id == payload.organization_id,
                    )
                )
                if finding is None:
                    raise NotFoundError("ai_source_not_found", "AI source was not found.")
                data = {
                    "rule_key": finding.rule_key,
                    "rule_version": finding.rule_version,
                    "severity": finding.severity.value,
                    "status": finding.status.value,
                    "category": finding.category,
                    "evidence": finding.evidence_json,
                }
                version = finding.lifecycle_version
            elif source.source_type == AISourceType.RISK_ASSESSMENT:
                risk_assessment = self.db.scalar(
                    select(RiskAssessment).where(
                        RiskAssessment.id == source.source_id,
                        RiskAssessment.organization_id == payload.organization_id,
                    )
                )
                if risk_assessment is None:
                    raise NotFoundError("ai_source_not_found", "AI source was not found.")
                data = {
                    "status": risk_assessment.status.value,
                    "aggregate_score": risk_assessment.aggregate_score,
                    "aggregate_priority": (
                        risk_assessment.aggregate_priority.value
                        if risk_assessment.aggregate_priority
                        else None
                    ),
                    "findings_total": risk_assessment.findings_total,
                }
                version = 1
            else:
                compliance_assessment = self.db.scalar(
                    select(ComplianceAssessment).where(
                        ComplianceAssessment.id == source.source_id,
                        ComplianceAssessment.organization_id == payload.organization_id,
                    )
                )
                if compliance_assessment is None:
                    raise NotFoundError("ai_source_not_found", "AI source was not found.")
                data = {
                    "status": compliance_assessment.status.value,
                    "framework_id": str(compliance_assessment.framework_id),
                }
                version = 1
            safe = sanitize(data)
            digest = hashlib.sha256(canonical_json(safe).encode()).hexdigest()
            reference = f"{source.source_type.value}:{source.source_id}:v{version}"
            sources.append({"reference": reference, "data": safe})
            rows.append(
                {
                    "source_type": source.source_type,
                    "source_id": source.source_id,
                    "source_version": version,
                    "source_hash": digest,
                }
            )
        return {"task": payload.task_type.value, "sources": sources}, rows
