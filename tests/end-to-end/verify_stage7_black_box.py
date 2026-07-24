from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(SUPPORT))
from stage7_black_box_contract import STEP_DESCRIPTIONS, StepResult, load_results  # noqa: E402


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> int:
    output_dir = Path(
        os.environ.get(
            "STAGE7_BLACK_BOX_OUTPUT_DIR",
            Path(tempfile.gettempdir()) / "cloudops-stage7-black-box",
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_result = output_dir / "backend.json"
    frontend_result = output_dir / "frontend.json"
    for stale_result in (backend_result, frontend_result):
        stale_result.unlink(missing_ok=True)
    env = os.environ.copy()
    if not env.get("POSTGRES_TEST_DATABASE_URL"):
        raise SystemExit("POSTGRES_TEST_DATABASE_URL is required")
    env["STAGE7_BLACK_BOX_BACKEND_RESULTS"] = str(backend_result)
    env["STAGE7_BLACK_BOX_FRONTEND_RESULTS"] = str(frontend_result)
    python = ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
    run([str(python), "-m", "alembic", "upgrade", "head"], ROOT / "apps" / "api", env)
    run(
        [str(python), "-m", "pytest", "app/tests/test_stage7_black_box.py", "-q"],
        ROOT / "apps" / "api",
        env,
    )
    run(
        ["npm.cmd", "run", "test", "--", "--run", "src/test/stage7BlackBox.test.tsx"],
        ROOT / "apps" / "web",
        env,
    )
    combined = load_results(backend_result) + load_results(frontend_result)
    by_step: dict[int, StepResult] = {}
    for result in combined:
        if result.step in by_step:
            raise SystemExit(f"duplicate step result: {result.step}")
        if result.description != STEP_DESCRIPTIONS.get(result.step):
            raise SystemExit(f"incorrect description for step {result.step}")
        by_step[result.step] = result
    missing = sorted(set(STEP_DESCRIPTIONS) - set(by_step))
    failed = sorted(step for step, result in by_step.items() if result.status != "PASS")
    if missing or failed:
        raise SystemExit(
            f"black-box verification failed; missing={missing}, failed={failed}"
        )
    ordered = [by_step[step] for step in sorted(by_step)]
    json_path = output_dir / "stage7-black-box.json"
    markdown_path = output_dir / "stage7-black-box.md"
    json_path.write_text(
        json.dumps([asdict(item) for item in ordered], indent=2), encoding="utf-8"
    )
    rows = [
        "# Stage 7 Black-box Verification",
        "",
        "| Step | Status | Evidence |",
        "|---:|---|---|",
    ]
    rows.extend(
        f"| {item.step} | {item.status} | {item.evidence.replace('|', '/')} |"
        for item in ordered
    )
    markdown_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(
        f"Stage 7 black-box contract: 44 PASS; JSON={json_path}; Markdown={markdown_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
