from __future__ import annotations

from typing import Any, Protocol

from app.models.enums import AITaskType
from app.schemas.ai import AIContent


class AIProvider(Protocol):
    key: str

    def generate(self, task: AITaskType, context: dict[str, Any]) -> AIContent: ...


class MockAIProvider:
    """Deterministic, offline provider used by every environment until explicitly replaced."""

    key = "mock"

    def generate(self, task: AITaskType, context: dict[str, Any]) -> AIContent:
        references = [str(item["reference"]) for item in context["sources"]]
        labels = {
            AITaskType.EXPLAIN_FINDING: "Finding explanation",
            AITaskType.EXPLAIN_BUSINESS_IMPACT: "Business impact explanation",
            AITaskType.SUGGEST_REMEDIATION: "Remediation suggestion",
            AITaskType.EXECUTIVE_SUMMARY: "Executive summary",
            AITaskType.JIRA_DESCRIPTION: "Jira description draft",
            AITaskType.EMAIL_SUMMARY: "Email summary draft",
        }
        return AIContent(
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
