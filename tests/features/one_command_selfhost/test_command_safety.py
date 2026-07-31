from __future__ import annotations

from pathlib import Path

import pytest

from scripts.selfhost.cloudops import (
    LOG_TARGETS,
    Controller,
    bounded_backup_path,
    parser,
    redact,
)
from scripts.selfhost.errors import SelfHostError


def test_all_required_commands_parse() -> None:
    for command in (
        "up",
        "demo-up",
        "verify",
        "status",
        "logs",
        "restart",
        "update",
        "backup",
        "restore",
        "down",
        "destroy",
    ):
        assert parser().parse_args([command]).command == command
    assert LOG_TARGETS == (
        "all",
        "postgres",
        "api",
        "web",
        "worker",
        "scheduler",
        "cloudflared",
        "migration",
    )


def test_destroy_refuses_without_exact_confirmation(tmp_path: Path) -> None:
    controller = Controller(tmp_path)
    for confirmation in (None, "yes", "DESTROY"):
        with pytest.raises(SelfHostError) as caught:
            controller.destroy(confirmation)
        assert caught.value.code == "DESTROY_CONFIRMATION_REQUIRED"


def test_restore_path_cannot_escape_backup_directory(tmp_path: Path) -> None:
    root = tmp_path / ".cloudops" / "backups"
    root.mkdir(parents=True)
    with pytest.raises(SelfHostError) as caught:
        bounded_backup_path(root, Path("../../outside.dump"))
    assert caught.value.code == "RESTORE_PATH_OUTSIDE_BACKUP_DIRECTORY"


def test_restore_path_accepts_only_bounded_path(tmp_path: Path) -> None:
    root = tmp_path / ".cloudops" / "backups"
    root.mkdir(parents=True)
    requested = Path(".cloudops/backups/safe.dump")
    assert bounded_backup_path(root, requested) == (root / "safe.dump").resolve()


def test_log_redaction_removes_common_secret_forms() -> None:
    output = redact(
        "token=synthetic-value password: another-value Authorization: Bearer fake-token "
        "CLOUDFLARE_TUNNEL_TOKEN=third-value"
    )
    assert "synthetic-value" not in output
    assert "another-value" not in output
    assert "fake-token" not in output
    assert "third-value" not in output
    assert "[REDACTED]" in output


def test_restore_rejects_malformed_metadata_before_compose(tmp_path: Path) -> None:
    root = tmp_path / ".cloudops" / "backups"
    root.mkdir(parents=True)
    dump = root / "broken.dump"
    dump.write_bytes(b"synthetic")
    dump.with_suffix(".json").write_text("{invalid", encoding="utf-8")
    controller = Controller(tmp_path)
    with pytest.raises(SelfHostError) as caught:
        controller.restore(Path(".cloudops/backups/broken.dump"), "RESTORE-CLOUDOPS-DATA")
    assert caught.value.code == "RESTORE_BACKUP_INVALID"
