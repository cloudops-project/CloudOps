from __future__ import annotations

from enum import StrEnum
from time import monotonic
from typing import Any, Protocol

from app.models.enums import AITaskType
from app.schemas.ai import AIContent


class AIProvider(Protocol):
    key: str

    def generate(
        self,
        task: AITaskType,
        context: dict[str, Any],
        control: ProviderExecutionControl,
    ) -> AIContent: ...


class ProviderErrorCode(StrEnum):
    DISABLED = "AI_PROVIDER_DISABLED"
    TIMEOUT = "AI_PROVIDER_TIMEOUT"
    RETRYABLE = "AI_PROVIDER_RETRYABLE"
    FAILED = "AI_PROVIDER_FAILED"
    INVALID_RESPONSE = "AI_INVALID_RESPONSE"


class AIProviderError(Exception):
    def __init__(self, code: ProviderErrorCode, *, retryable: bool = False) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable


class ProviderExecutionControl:
    def __init__(self, timeout_seconds: float) -> None:
        self.deadline = monotonic() + timeout_seconds
        self.cancelled = False
        self.events: list[str] = []

    def start(self) -> None:
        self.events.append("invocation_started")

    def cancel(self) -> None:
        if not self.cancelled:
            self.cancelled = True
            self.events.append("cancellation_received")

    def ensure_active(self) -> None:
        if self.cancelled or monotonic() >= self.deadline:
            self.cancel()
            raise AIProviderError(ProviderErrorCode.TIMEOUT)

    def exit(self) -> None:
        self.events.append("invocation_exited")


class MockAIProvider:
    """Deterministic, offline provider used by every environment until explicitly replaced."""

    key = "mock"
    model = "cloudops-deterministic-mock-v1"
    enabled = True

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0
        self.lifecycle_events: list[str] = []

    def generate(
        self,
        task: AITaskType,
        context: dict[str, Any],
        control: ProviderExecutionControl | None = None,
    ) -> AIContent:
        control = control or ProviderExecutionControl(10.0)
        self.invocations += 1
        control.start()
        self.lifecycle_events.append("invocation_started")
        if not self.enabled or self.fault_mode == "disabled":
            control.exit()
            raise AIProviderError(ProviderErrorCode.DISABLED)
        if self.fault_mode == "timeout" or (
            self.fault_mode == "transient_then_timeout" and self.invocations > 1
        ):
            control.cancel()
            self.lifecycle_events.extend(["cancellation_received", "invocation_exited"])
            control.exit()
            raise AIProviderError(ProviderErrorCode.TIMEOUT)
        if self.fault_mode == "late_success":
            control.cancel()
            self.lifecycle_events.extend(
                [
                    "cancellation_received",
                    "result_attempted",
                    "result_rejected",
                    "invocation_exited",
                ]
            )
            control.exit()
            raise AIProviderError(ProviderErrorCode.TIMEOUT)
        if self.fault_mode == "permanent_failure":
            control.exit()
            raise AIProviderError(ProviderErrorCode.FAILED)
        if self.fault_mode in {
            "transient_then_success",
            "transient_then_timeout",
            "transient_always",
        } and (self.invocations == 1 or self.fault_mode == "transient_always"):
            control.exit()
            raise AIProviderError(ProviderErrorCode.RETRYABLE, retryable=True)
        if self.fault_mode in {"invalid_json", "schema_invalid"}:
            control.exit()
            raise AIProviderError(ProviderErrorCode.INVALID_RESPONSE)
        if self.fault_mode == "oversized":
            control.exit()
            return AIContent.model_construct(
                title="Oversized",
                summary="x" * 3000,
                details=[],
                caveats=[],
                source_references=[],
                draft_only=True,
            )
        references = [str(item["reference"]) for item in context["sources"]]
        labels = {
            AITaskType.EXPLAIN_FINDING: "Finding explanation",
            AITaskType.EXPLAIN_BUSINESS_IMPACT: "Business impact explanation",
            AITaskType.SUGGEST_REMEDIATION: "Remediation suggestion",
            AITaskType.EXECUTIVE_SUMMARY: "Executive summary",
            AITaskType.JIRA_DESCRIPTION: "Jira description draft",
            AITaskType.EMAIL_SUMMARY: "Email summary draft",
        }
        control.ensure_active()
        result = AIContent(
            title=labels[task],
            summary=(
                "This draft explains persisted deterministic CloudOps evidence. "
                "It does not create findings, change severity, or calculate risk."
            ),
            details=[
                f"Task: {task.value}.",
                f"Evidence sources reviewed: {len(references)}.",
                "Validate this draft against the linked source records before operational use.",
            ],
            caveats=[
                "AI output may be incomplete or inaccurate.",
                "No remediation, ticket, or message was executed or sent.",
            ],
            source_references=references,
            draft_only=True,
        )
        self.lifecycle_events.extend(["result_attempted", "invocation_exited"])
        control.exit()
        return result
