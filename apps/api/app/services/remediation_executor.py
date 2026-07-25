from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RemediationExecutionOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class RemediationExecutionResult:
    outcome: RemediationExecutionOutcome
    before_state: dict[str, object]
    after_state: dict[str, object] | None = None
    sanitized_error: str | None = None


class RemediationExecutor(Protocol):
    key: str

    def execute(
        self,
        *,
        rule_key: str,
        finding_id: uuid.UUID,
        context: dict[str, object],
    ) -> RemediationExecutionResult: ...


class MockRemediationExecutor:
    """Deterministic, offline remediation executor. The only executor
    available in Stage 10; performs no AWS calls, no sleeps, and no
    background work, and never mutates a real customer resource. Real
    executors are intentionally out of scope for Version 1 and must
    implement the same Protocol."""

    key = "mock"

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0

    def execute(
        self,
        *,
        rule_key: str,
        finding_id: uuid.UUID,
        context: dict[str, object],
    ) -> RemediationExecutionResult:
        self.invocations += 1
        before_state = {
            "simulated": True,
            "rule_key": rule_key,
            "finding_id": str(finding_id),
            "attempt": self.invocations,
        }
        if self.fault_mode == "success":
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.SUCCESS,
                before_state=before_state,
                after_state={"simulated_remediated": True, **context},
            )
        if self.fault_mode == "always_fail":
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.FAILURE,
                before_state=before_state,
                sanitized_error="Mock executor was configured to fail execution.",
            )
        if self.fault_mode == "fail_then_succeed" and self.invocations == 1:
            return RemediationExecutionResult(
                outcome=RemediationExecutionOutcome.FAILURE,
                before_state=before_state,
                sanitized_error="Mock executor transient failure.",
            )
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.SUCCESS,
            before_state=before_state,
            after_state={"simulated_remediated": True, **context},
        )
