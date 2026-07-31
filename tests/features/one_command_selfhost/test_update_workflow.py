from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.selfhost.cloudops import Controller
from scripts.selfhost.errors import SelfHostError


class RecordingRunner:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.responses = responses
        self.commands: list[list[str]] = []

    def run(
        self, command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        code, output = self.responses.pop(0)
        return subprocess.CompletedProcess(command, code, stdout=output, stderr="")


def test_update_refuses_feature_branch_before_backup(tmp_path: Path) -> None:
    controller = Controller(tmp_path)
    runner = RecordingRunner([(0, "feature\n")])
    controller.runner = runner  # type: ignore[assignment]
    backup_called = False

    def backup() -> Path:
        nonlocal backup_called
        backup_called = True
        return tmp_path / "should-not-exist.dump"

    controller.backup = backup  # type: ignore[method-assign]
    with pytest.raises(SelfHostError) as caught:
        controller.update()
    assert caught.value.code == "UPDATE_GIT_BRANCH_UNSUPPORTED"
    assert not backup_called


def test_update_refuses_dirty_main_before_backup(tmp_path: Path) -> None:
    controller = Controller(tmp_path)
    runner = RecordingRunner([(0, "main\n"), (0, " M local-change\n")])
    controller.runner = runner  # type: ignore[assignment]
    backup_called = False

    def backup() -> Path:
        nonlocal backup_called
        backup_called = True
        return tmp_path / "should-not-exist.dump"

    controller.backup = backup  # type: ignore[method-assign]
    with pytest.raises(SelfHostError) as caught:
        controller.update()
    assert caught.value.code == "UPDATE_GIT_WORKTREE_DIRTY"
    assert not backup_called
