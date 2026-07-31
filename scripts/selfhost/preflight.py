from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scripts.selfhost.errors import SelfHostError


class CommandRunner(Protocol):
    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass(slots=True)
class SystemRunner:
    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            text=True,
            cwd=cwd,
            capture_output=capture_output,
            env=env,
        )


def require_repository(root: Path, runner: CommandRunner) -> None:
    result = runner.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
    )
    if result.returncode or Path(result.stdout.strip()).resolve() != root.resolve():
        raise SelfHostError(
            "PRECHECK_GIT_REPOSITORY_INVALID",
            "The command is not running from the CloudOps repository root.",
            "Change to the cloned CloudOps directory and rerun.",
        )


def require_tools(runner: CommandRunner) -> None:
    if shutil.which("docker") is None:
        raise SelfHostError(
            "PRECHECK_DOCKER_UNAVAILABLE",
            "Docker is not installed or is not on PATH.",
            "Install Docker Engine or Docker Desktop and rerun.",
        )
    version = runner.run(["docker", "compose", "version"], capture_output=True)
    if version.returncode:
        raise SelfHostError(
            "PRECHECK_COMPOSE_UNAVAILABLE",
            "Docker Compose v2 is unavailable.",
            "Install the Docker Compose v2 plugin and rerun.",
        )
    daemon = runner.run(["docker", "info"], capture_output=True)
    if daemon.returncode:
        raise SelfHostError(
            "PRECHECK_DOCKER_DAEMON_UNAVAILABLE",
            "Docker is installed but the daemon is not reachable.",
            "Start Docker Desktop or the Docker service, then rerun.",
        )


def resource_warnings(root: Path) -> list[str]:
    warnings: list[str] = []
    cpus = os.cpu_count() or 1
    if cpus < 4:
        warnings.append(
            f"PRECHECK_CPU_RECOMMENDATION: {cpus} cores available; 4 recommended."
        )
    available_memory = _available_memory_bytes()
    if available_memory is not None and available_memory < 8 * 1024**3:
        warnings.append("PRECHECK_MEMORY_RECOMMENDATION: less than 8 GiB available.")
    free_disk = shutil.disk_usage(root).free
    if free_disk < 30 * 1024**3:
        warnings.append("PRECHECK_DISK_RECOMMENDATION: less than 30 GiB free.")
    return warnings


def _available_memory_bytes() -> int | None:
    if platform.system() == "Windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong),
                    ("available", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong),
                    ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.available)
        except (AttributeError, OSError):
            return None
    memory_info = Path("/proc/meminfo")
    if memory_info.exists():
        for line in memory_info.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    return None


def run_preflight(root: Path, runner: CommandRunner) -> list[str]:
    require_repository(root, runner)
    require_tools(runner)
    return resource_warnings(root)
