from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import RuleResultStatus

_SENSITIVE = re.compile(
    r"(access.?key|secret|session.?token|credential|password|authorization|cookie)", re.I
)
MAX_EVIDENCE_ITEMS = 50
MAX_EVIDENCE_STRING = 1000


def sanitize_evidence(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key)[:120]: sanitize_evidence(item, depth=depth + 1)
            for key, item in list(value.items())[:MAX_EVIDENCE_ITEMS]
            if not _SENSITIVE.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence(item, depth=depth + 1) for item in value[:MAX_EVIDENCE_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_EVIDENCE_STRING]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:MAX_EVIDENCE_STRING]


@dataclass(frozen=True)
class RuleResult:
    status: RuleResultStatus
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", sanitize_evidence(self.evidence))


def passed(**evidence: Any) -> RuleResult:
    return RuleResult(RuleResultStatus.PASSED, evidence)


def failed(**evidence: Any) -> RuleResult:
    return RuleResult(RuleResultStatus.FAILED, evidence)


def not_applicable(reason: str) -> RuleResult:
    return RuleResult(RuleResultStatus.NOT_APPLICABLE, {"reason": reason})


def error(code: str = "invalid_or_incomplete_metadata") -> RuleResult:
    return RuleResult(RuleResultStatus.ERROR, {}, code)
