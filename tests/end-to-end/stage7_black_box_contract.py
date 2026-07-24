from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

STEP_DESCRIPTIONS = {
    1: "Register a synthetic owner.",
    2: "Create a synthetic organization.",
    3: "Create a synthetic AWS account and assets without contacting AWS.",
    4: "Run Stage 4 deterministic finding evaluation.",
    5: "Run Stage 5 deterministic compliance assessment.",
    6: "Run Stage 6 deterministic risk assessment.",
    7: "Generate all supported finding AI tasks.",
    8: "Generate supported risk summaries.",
    9: "Generate supported compliance summaries.",
    10: "Validate every response against the public schema.",
    11: "Verify source and provider metadata.",
    12: "Verify advisory, draft-only, and human-review labels.",
    13: "Verify clipboard success.",
    14: "Verify clipboard failure.",
    15: "Verify no email is delivered.",
    16: "Verify no Jira issue is created.",
    17: "Verify no remediation executes.",
    18: "Verify no AWS resource changes occur.",
    19: "Verify Stage 1-6 authoritative state is unchanged.",
    20: "Replay the same key and same context.",
    21: "Reuse the same key with a changed task.",
    22: "Reuse the same key with a changed source.",
    23: "Reuse the same key after deterministic source change.",
    24: "Exhaust quota and verify AI_RATE_LIMITED.",
    25: "Verify provider-disabled behavior.",
    26: "Verify timeout and cooperative cancellation.",
    27: "Verify transient provider retry followed by success.",
    28: "Verify permanent provider failure.",
    29: "Verify invalid structured response.",
    30: "Verify oversized response rejection.",
    31: "Verify all prompt-injection categories.",
    32: "Verify all redaction categories.",
    33: "Verify all six roles.",
    34: "Verify missing, malformed, and expired JWTs.",
    35: "Verify absent, suspended, and removed memberships.",
    36: "Verify every cross-tenant source type.",
    37: "Verify random UUID probing.",
    38: "Switch organizations and verify frontend cache isolation.",
    39: "Log out and verify protected cache clearing.",
    40: "Change deterministic finding source data.",
    41: "Verify historical AI output becomes stale.",
    42: "Generate a new response with a new idempotency key.",
    43: "Verify the original historical response remains unchanged.",
    44: "Verify the new response records current source identity.",
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
            raise AssertionError(f"Unknown Stage 7 black-box step: {step}")
        if step in self.results:
            raise AssertionError(f"Duplicate Stage 7 black-box step: {step}")
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

    def write_partial(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                [asdict(self.results[key]) for key in sorted(self.results)], indent=2
            ),
            encoding="utf-8",
        )

    def finalize(self) -> list[StepResult]:
        missing = sorted(set(STEP_DESCRIPTIONS) - set(self.results))
        failed = sorted(
            key for key, result in self.results.items() if result.status != "PASS"
        )
        if missing or failed:
            raise AssertionError(
                f"Stage 7 black-box contract failed; missing={missing}, failed={failed}"
            )
        return [self.results[key] for key in sorted(self.results)]


def load_results(path: Path) -> list[StepResult]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [StepResult(**item) for item in raw]
