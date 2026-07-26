from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

STEP_DESCRIPTIONS = {
    1: "Register and log in as the demo owner.",
    2: "Create a demo organization.",
    3: "Create a synthetic connected AWS account without real AWS.",
    4: "Seed synthetic inventory without invoking AWS discovery.",
    5: "View the dashboard summary.",
    6: "View assets.",
    7: "Run deterministic findings evaluation and view findings.",
    8: "Run compliance assessment and view compliance.",
    9: "Run risk assessment and view risk.",
    10: "Generate and view an advisory AI explanation.",
    11: "View notification history.",
    12: "Approve and deliver a notification.",
    13: "Propose, approve, and execute mock remediation.",
    14: "Create a schedule and trigger run-now.",
    15: "View the audit trail.",
    16: "Export audit CSV.",
    17: "Verify no real AWS, external AI, email, Jira, or remediation side effect escaped.",
    18: "Verify generated demo state is tenant-scoped and complete.",
}


@dataclass(frozen=True)
class StepResult:
    step: int
    description: str
    status: str
    evidence: str
    duration_ms: int


class StepRecorder:
    def __init__(self) -> None:
        self.results: dict[int, StepResult] = {}

    def record(self, step: int, evidence: str, operation: Callable[[], None]) -> None:
        if step not in STEP_DESCRIPTIONS:
            raise AssertionError(f"Unknown V1 demo step: {step}")
        if step in self.results:
            raise AssertionError(f"Duplicate V1 demo step: {step}")
        started = time.perf_counter()
        try:
            operation()
        except Exception as exc:
            self.results[step] = StepResult(
                step,
                STEP_DESCRIPTIONS[step],
                "FAIL",
                f"{evidence}: {type(exc).__name__}: {exc}",
                round((time.perf_counter() - started) * 1000),
            )
            raise
        self.results[step] = StepResult(
            step,
            STEP_DESCRIPTIONS[step],
            "PASS",
            evidence,
            round((time.perf_counter() - started) * 1000),
        )

    def finalize(self, path: Path) -> None:
        missing = sorted(set(STEP_DESCRIPTIONS) - set(self.results))
        failed = sorted(step for step, result in self.results.items() if result.status != "PASS")
        if missing or failed:
            raise AssertionError(f"V1 demo contract failed; missing={missing}; failed={failed}")
        rows = [asdict(self.results[step]) for step in sorted(self.results)]
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def load_results(path: Path) -> list[StepResult]:
    return [StepResult(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
