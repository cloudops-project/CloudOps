from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import NoReturn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.selfhost.configure import configure, read_env
from scripts.selfhost.errors import SelfHostError
from scripts.selfhost.healthcheck import (
    EXPECTED_MIGRATION_HEAD,
    HealthResult,
    assert_healthy,
    container_health,
    public_https_health,
    verify_migration,
    wait_until,
)
from scripts.selfhost.preflight import SystemRunner, run_preflight

PROJECT = "cloudops-selfhost"
COMPOSE_FILE = "compose.selfhost.yml"
SERVICES = ("postgres", "api", "web", "worker", "scheduler", "cloudflared", "migration")
LOG_TARGETS = ("all", *SERVICES)
SECRET_NAMES = (
    "postgres_password",
    "jwt_secret_key",
    "jira_token_encryption_key",
    "cloudflare_tunnel_token",
)
REDACTION_PATTERNS = (
    re.compile(r"(?i)bearer\s+[^\s]+"),
    re.compile(
        r"(?i)([a-z0-9_]*(?:token|password|secret|authorization)[a-z0-9_]*)"
        r"([\"'=:\s]+)([^\s,\"']+)"
    ),
)


class Controller:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.runner = SystemRunner()
        self.project = os.getenv("CLOUDOPS_COMPOSE_PROJECT", PROJECT)
        self.env_file = self.root / ".env.selfhost"
        self.runtime_dir = self.root / ".cloudops" / "runtime"
        self.backup_dir = self.root / ".cloudops" / "backups"

    def compose(
        self, *arguments: str, capture: bool = False
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(self.root / COMPOSE_FILE),
            *arguments,
        ]
        result = self.runner.run(
            command,
            cwd=self.root,
            capture_output=capture,
        )
        if result.returncode:
            detail = redact((result.stderr or result.stdout or "").strip())
            raise SelfHostError(
                "COMPOSE_COMMAND_FAILED",
                f"Docker Compose failed for `{arguments[0] if arguments else 'command'}`. {detail}",
                "Inspect Docker status and the named service logs, then rerun.",
                result.returncode,
            )
        return result

    def config(self, *, interactive: bool) -> dict[str, str]:
        return configure(self.root, interactive=interactive)

    def validate_rendered_config(self) -> None:
        rendered = self.compose("config", capture=True).stdout
        for name in SECRET_NAMES:
            path = self.runtime_dir / name
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value and value in rendered:
                    raise SelfHostError(
                        "CONFIG_SECRET_IN_COMPOSE_OUTPUT",
                        f"Generated Compose output contains the {name} value.",
                        "Keep credentials in Docker secret files and remove direct interpolation.",
                    )
        forbidden = (
            "0.0.0.0:5432",
            "0.0.0.0:8000",
            '"APP_ENV": "development"',
            '"DEMO_SYNTHETIC_DISCOVERY": "true"',
        )
        if any(value in rendered for value in forbidden):
            raise SelfHostError(
                "CONFIG_PRODUCTION_UNSAFE_COMPOSE",
                "Rendered Compose configuration exposes a forbidden production setting.",
                "Remove public data/API ports and development-only settings.",
            )

    def up(self) -> None:
        for warning in run_preflight(self.root, self.runner):
            print(f"WARNING: {warning}")
        values = self.config(interactive=sys.stdin.isatty())
        self.validate_rendered_config()
        print("Building CloudOps images...")
        self.compose("build", "api", "worker", "scheduler", "web", "cloudflared")
        self.compose("up", "-d", "postgres")
        self.compose(
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            "migration",
            "migration",
        )
        self.compose("up", "-d", "api", "worker", "scheduler", "web")
        self.verify(include_public=False)
        self.compose("up", "-d", "cloudflared")
        self.verify(include_public=True)
        self._print_ready(values["CLOUDOPS_DOMAIN"])

    def demo_up(self) -> None:
        env = os.environ.copy()
        if env.get("APP_ENV", "development").casefold() == "production":
            raise SelfHostError(
                "DEMO_PRODUCTION_REFUSED",
                "Quick Tunnel demo mode cannot run with APP_ENV=production.",
                "Unset APP_ENV or use the named-tunnel `up` command.",
            )
        if os.name == "nt":
            command = [
                "powershell",
                "-NoProfile",
                "-File",
                str(self.root / "scripts" / "demo_bootstrap.ps1"),
                "-Reset",
                "-Tunnel",
            ]
        else:
            raise SelfHostError(
                "DEMO_SHELL_HELPER_UNAVAILABLE",
                "The existing seeded demo bootstrap currently requires PowerShell.",
                "Install PowerShell 7, or run the documented Compose demo sequence.",
            )
        result = self.runner.run(command, cwd=self.root, env=env)
        if result.returncode:
            raise SelfHostError(
                "DEMO_START_FAILED",
                "The temporary synthetic demo did not start.",
                "Inspect demo service logs and rerun `demo-up`.",
                result.returncode,
            )
        print(
            "WARNING: Quick Tunnel is temporary; its URL changes and stops with cloudflared."
        )

    def verify(self, *, include_public: bool = True) -> None:
        results = []
        for service in ("postgres", "api", "web", "worker", "scheduler"):
            result = wait_until(
                partial(self._probe_service, service),
                timeout_seconds=120,
                interval_seconds=3,
            )
            results.append(result)
        migration = self.compose(
            "run",
            "--rm",
            "--no-deps",
            "migration",
            "/app/scripts/selfhost-container-env.sh",
            "python",
            "-m",
            "alembic",
            "current",
            capture=True,
        )
        results.append(verify_migration(migration.stdout))
        if include_public:
            tunnel_id = self.compose(
                "ps", "-q", "cloudflared", capture=True
            ).stdout.strip()
            if not tunnel_id:
                raise SelfHostError(
                    "HEALTH_CLOUDFLARE_TUNNEL_DOWN",
                    "The named Cloudflare Tunnel container is not running.",
                    "Verify the named tunnel token and inspect cloudflared logs.",
                )
            inspect = self.runner.run(
                ["docker", "inspect", tunnel_id], capture_output=True
            )
            tunnel = container_health(inspect.stdout, "cloudflared")
            if tunnel.status != "running":
                assert_healthy(tunnel)
            results.append(tunnel)
            domain = read_env(self.env_file).get("CLOUDOPS_DOMAIN", "")
            results.append(
                wait_until(
                    lambda: public_https_health(domain),
                    timeout_seconds=60,
                    interval_seconds=5,
                )
            )
        for result in results:
            print(f"{result.component}: {result.status} ({result.detail})")

    def status(self) -> None:
        values = read_env(self.env_file)
        self.compose("ps")
        print(
            f"Application: https://{values.get('CLOUDOPS_DOMAIN', '<not-configured>')}"
        )
        print(f"Migration: {EXPECTED_MIGRATION_HEAD}")
        volumes = self.runner.run(
            ["docker", "volume", "inspect", "cloudops_postgres"],
            capture_output=True,
        )
        print(
            f"Persistent volume: {'present' if volumes.returncode == 0 else 'missing'}"
        )
        self.compose("images")

    def logs(self, target: str) -> None:
        if target not in LOG_TARGETS:
            raise SelfHostError(
                "LOG_TARGET_INVALID",
                f"Unsupported log target: {target}",
                f"Choose one of: {', '.join(LOG_TARGETS)}.",
            )
        targets = list(SERVICES) if target == "all" else [target]
        result = self.compose(
            "logs", "--no-color", "--tail", "200", *targets, capture=True
        )
        print(redact(result.stdout))

    def restart(self) -> None:
        self._require_initialized()
        self.compose("restart", "api", "worker", "scheduler", "web", "cloudflared")
        self.verify()

    def down(self) -> None:
        self.compose("down")
        print(
            "CloudOps stopped. Persistent database, configuration, and backups were preserved."
        )

    def destroy(self, confirmation: str | None) -> None:
        if confirmation != "DESTROY-CLOUDOPS-DATA":
            raise SelfHostError(
                "DESTROY_CONFIRMATION_REQUIRED",
                "Destroy deletes containers, the PostgreSQL volume, and local runtime secrets.",
                "Rerun with `destroy --confirm DESTROY-CLOUDOPS-DATA`.",
            )
        self.compose("down", "--volumes", "--remove-orphans")
        if self.runtime_dir.exists():
            shutil.rmtree(self.runtime_dir)
        self.env_file.unlink(missing_ok=True)
        print(
            "Local CloudOps containers, database volume, configuration, and runtime secrets deleted."
        )
        print("External Cloudflare tunnel and DNS resources were not changed.")

    def backup(self) -> Path:
        self._require_initialized()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = self.backup_dir / f"cloudops-{stamp}.dump"
        if destination.exists():
            raise SelfHostError(
                "BACKUP_DESTINATION_EXISTS",
                "The timestamped backup destination already exists.",
                "Wait one second and rerun; existing backups are never overwritten.",
            )
        values = read_env(self.env_file)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(self.root / COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            values["POSTGRES_USER"],
            "-d",
            values["POSTGRES_DB"],
            "-Fc",
        ]
        with destination.open("xb") as handle:
            result = subprocess.run(
                command,
                cwd=self.root,
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode:
            destination.unlink(missing_ok=True)
            raise SelfHostError(
                "BACKUP_DATABASE_DUMP_FAILED",
                "PostgreSQL did not create a backup.",
                "Verify database health and free disk space, then rerun.",
                result.returncode,
            )
        metadata = {
            "format": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "git_sha": self._git_sha(),
            "alembic_head": EXPECTED_MIGRATION_HEAD,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "database": values["POSTGRES_DB"],
        }
        metadata_path = destination.with_suffix(".json")
        metadata_path.write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        _restrict(destination)
        _restrict(metadata_path)
        print(f"Backup created: {destination.relative_to(self.root)}")
        return destination

    def restore(self, backup: Path | None, confirmation: str | None) -> None:
        if backup is None:
            raise SelfHostError(
                "RESTORE_BACKUP_REQUIRED",
                "A backup path is required.",
                "Run `cloudops restore .cloudops/backups/<name>.dump --confirm RESTORE-CLOUDOPS-DATA`.",
            )
        target = bounded_backup_path(self.backup_dir, backup)
        metadata_path = target.with_suffix(".json")
        if not target.is_file() or not metadata_path.is_file():
            raise SelfHostError(
                "RESTORE_BACKUP_INVALID",
                "The dump or its metadata file is missing.",
                "Choose an intact backup created by `cloudops backup`.",
            )
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SelfHostError(
                "RESTORE_BACKUP_INVALID",
                "Backup metadata is unreadable or malformed.",
                "Choose an intact backup created by `cloudops backup`.",
            ) from exc
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if metadata.get("sha256") != digest or metadata.get("format") != 1:
            raise SelfHostError(
                "RESTORE_BACKUP_CORRUPTED",
                "Backup integrity validation failed.",
                "Use a different verified backup.",
            )
        if confirmation != "RESTORE-CLOUDOPS-DATA":
            raise SelfHostError(
                "RESTORE_CONFIRMATION_REQUIRED",
                "Restore replaces the current CloudOps database.",
                "Rerun with `--confirm RESTORE-CLOUDOPS-DATA` after taking a backup.",
            )
        tunnel_was_running = self._service_running("cloudflared")
        values = read_env(self.env_file)
        if metadata.get("database") != values.get("POSTGRES_DB"):
            raise SelfHostError(
                "RESTORE_DATABASE_IDENTITY_MISMATCH",
                "The backup database identity does not match this installation.",
                "Select a backup created by this CloudOps installation.",
            )
        self.compose("stop", "api", "worker", "scheduler", "web")
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(self.root / COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            values["POSTGRES_USER"],
            "-d",
            values["POSTGRES_DB"],
            "--clean",
            "--if-exists",
            "--no-owner",
            "--exit-on-error",
            "--single-transaction",
        ]
        with target.open("rb") as handle:
            result = subprocess.run(command, cwd=self.root, stdin=handle, check=False)
        if result.returncode:
            raise SelfHostError(
                "RESTORE_DATABASE_FAILED",
                "PostgreSQL restore failed; application services remain stopped.",
                "Inspect database logs and restore a verified backup.",
                result.returncode,
            )
        self.compose(
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            "migration",
            "migration",
        )
        services = ["api", "worker", "scheduler", "web"]
        if tunnel_was_running:
            services.append("cloudflared")
        self.compose("up", "-d", *services)
        self.verify(include_public=tunnel_was_running)

    def update(self) -> None:
        branch = self.runner.run(
            ["git", "-C", str(self.root), "branch", "--show-current"],
            capture_output=True,
        )
        if branch.returncode or branch.stdout.strip() != "main":
            raise SelfHostError(
                "UPDATE_GIT_BRANCH_UNSUPPORTED",
                "Automatic update is supported only from the local main branch.",
                "Switch a clean installation to main and rerun; feature branches are never merged.",
            )
        status = self.runner.run(
            ["git", "-C", str(self.root), "status", "--porcelain"],
            capture_output=True,
        )
        if status.returncode or status.stdout.strip():
            raise SelfHostError(
                "UPDATE_GIT_WORKTREE_DIRTY",
                "The repository has local changes.",
                "Commit or preserve local work before running update.",
            )
        old_sha = self._git_sha()
        backup = self.backup()
        pull = self.runner.run(
            ["git", "-C", str(self.root), "pull", "--ff-only", "origin", "main"]
        )
        if pull.returncode:
            raise SelfHostError(
                "UPDATE_GIT_PULL_FAILED",
                "The reviewed main branch could not be fast-forwarded.",
                f"Current data is preserved and pre-update backup is {backup.name}.",
            )
        self.validate_rendered_config()
        self.compose("build", "api", "worker", "scheduler", "web", "cloudflared")
        self.compose(
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            "migration",
            "migration",
        )
        self.compose("up", "-d", "api", "worker", "scheduler", "web", "cloudflared")
        self.verify()
        print(f"Updated: {old_sha[:12]} -> {self._git_sha()[:12]}")

    def _require_initialized(self) -> None:
        if not self.env_file.is_file() or any(
            not (self.runtime_dir / name).is_file() for name in SECRET_NAMES
        ):
            raise SelfHostError(
                "CONFIG_RUNTIME_STATE_MISSING",
                "Self-host configuration or generated secrets are missing.",
                "Restore `.cloudops/runtime` from secure backup or run `cloudops up` to initialize.",
            )

    def _git_sha(self) -> str:
        result = self.runner.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True,
        )
        if result.returncode:
            return "unknown"
        return result.stdout.strip()

    def _service_running(self, service: str) -> bool:
        container_id = self.compose("ps", "-q", service, capture=True).stdout.strip()
        if not container_id:
            return False
        result = self.runner.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
            capture_output=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "running"

    def _probe_service(self, service: str) -> HealthResult:
        container_id = self.compose("ps", "-q", service, capture=True).stdout.strip()
        if not container_id:
            raise SelfHostError(
                f"HEALTH_{service.upper()}_MISSING",
                f"The {service} container is not running.",
                f"Start the stack and inspect `cloudops logs {service}`.",
            )
        inspected = self.runner.run(
            ["docker", "inspect", container_id], capture_output=True
        )
        if inspected.returncode:
            raise SelfHostError(
                f"HEALTH_{service.upper()}_INSPECT_FAILED",
                f"Docker could not inspect {service}.",
                "Verify the Docker daemon and rerun.",
            )
        return container_health(inspected.stdout, service)

    @staticmethod
    def _print_ready(domain: str) -> None:
        print("\nCloudOps is running.")
        print(f"Application: https://{domain}")
        print("Database: healthy")
        print(f"Migration: {EXPECTED_MIGRATION_HEAD}")
        print("API health: healthy")
        print("API readiness: ready")
        print("Web: healthy")
        print("Worker: healthy")
        print("Scheduler: healthy")
        print("Cloudflare Tunnel: connected")


def bounded_backup_path(root: Path, requested: Path) -> Path:
    candidate = requested if requested.is_absolute() else root.parents[1] / requested
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SelfHostError(
            "RESTORE_PATH_OUTSIDE_BACKUP_DIRECTORY",
            "Restore paths must remain inside .cloudops/backups.",
            "Choose a backup created by `cloudops backup`.",
        ) from exc
    return resolved


def redact(value: str) -> str:
    redacted = value
    for pattern in REDACTION_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}[REDACTED]"
                if match.lastindex == 3
                else "[REDACTED]"
            ),
            redacted,
        )
    return redacted


def _restrict(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="cloudops", description="CloudOps self-host controller"
    )
    sub = result.add_subparsers(dest="command", required=True)
    for name in (
        "up",
        "demo-up",
        "verify",
        "status",
        "restart",
        "update",
        "backup",
        "down",
    ):
        sub.add_parser(name)
    logs = sub.add_parser("logs")
    logs.add_argument("target", nargs="?", default="all", choices=LOG_TARGETS)
    restore = sub.add_parser("restore")
    restore.add_argument("backup", nargs="?", type=Path)
    restore.add_argument("--confirm")
    destroy = sub.add_parser("destroy")
    destroy.add_argument("--confirm")
    return result


def dispatch(controller: Controller, arguments: argparse.Namespace) -> None:
    command = arguments.command.replace("-", "_")
    method = getattr(controller, command)
    if arguments.command == "logs":
        method(arguments.target)
    elif arguments.command == "restore":
        method(arguments.backup, arguments.confirm)
    elif arguments.command == "destroy":
        method(arguments.confirm)
    else:
        method()


def fail(error: SelfHostError) -> NoReturn:
    print(str(error), file=sys.stderr)
    raise SystemExit(error.exit_code)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        dispatch(Controller(root), arguments)
    except SelfHostError as error:
        fail(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
