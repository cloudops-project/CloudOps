from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def heartbeat_path() -> Path | None:
    value = os.getenv("CLOUDOPS_HEARTBEAT_FILE", "").strip()
    return Path(value) if value else None


def touch(path: Path | None = None) -> None:
    target = path or heartbeat_path()
    if target is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()


def is_fresh(path: Path, max_age_seconds: float, *, now: float | None = None) -> bool:
    if not path.is_file():
        return False
    current = time.time() if now is None else now
    return 0 <= current - path.stat().st_mtime <= max_age_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description="CloudOps worker heartbeat utility")
    parser.add_argument("command", choices=("check", "touch"))
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--max-age", type=float, default=90.0)
    args = parser.parse_args()
    if args.command == "touch":
        touch(args.path)
        return 0
    return 0 if is_fresh(args.path, args.max_age) else 1


if __name__ == "__main__":
    raise SystemExit(main())
