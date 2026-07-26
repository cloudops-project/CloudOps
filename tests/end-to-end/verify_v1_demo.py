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
from v1_demo_contract import STEP_DESCRIPTIONS, load_results  # noqa: E402


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> int:
    output_dir = Path(
        os.environ.get("V1_DEMO_OUTPUT_DIR", Path(tempfile.gettempdir()) / "cloudops-v1-demo")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_result = output_dir / "backend.json"
    pytest_basetemp = output_dir / "pytest-temp"
    backend_result.unlink(missing_ok=True)
    env = os.environ.copy()
    if not env.get("POSTGRES_TEST_DATABASE_URL"):
        raise SystemExit("POSTGRES_TEST_DATABASE_URL is required")
    env["V1_DEMO_BACKEND_RESULTS"] = str(backend_result)
    python = ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
    run([str(python), "-m", "alembic", "upgrade", "head"], ROOT / "apps" / "api", env)
    run(
        [
            str(python),
            "-m",
            "pytest",
            "app/tests/test_v1_demo_black_box.py",
            "--basetemp",
            str(pytest_basetemp),
            "-q",
        ],
        ROOT / "apps" / "api",
        env,
    )
    results = load_results(backend_result)
    by_step = {result.step: result for result in results}
    missing = sorted(set(STEP_DESCRIPTIONS) - set(by_step))
    duplicate = len(results) - len(by_step)
    failed = sorted(step for step, result in by_step.items() if result.status != "PASS")
    if missing or duplicate or failed:
        raise SystemExit(
            "V1 demo verification failed; "
            f"missing={missing}; duplicate={duplicate}; failed={failed}"
        )
    json_path = output_dir / "v1-demo-black-box.json"
    md_path = output_dir / "v1-demo-black-box.md"
    json_path.write_text(
        json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8"
    )
    lines = [
        "# CloudOps V1 Demo Acceptance",
        "",
        "| Step | Status | Evidence |",
        "|---:|---|---|",
    ]
    lines.extend(
        f"| {result.step} | {result.status} | {result.evidence.replace('|', '/')} |"
        for result in results
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"CloudOps V1 demo contract: 18 PASS; JSON={json_path}; Markdown={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
