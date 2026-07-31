from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.selfhost.errors import SelfHostError
from scripts.selfhost.preflight import require_repository, require_tools


class FakeRunner:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = results

    def run(
        self, _command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return self.results.pop(0)


def completed(code: int, output: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=output, stderr="")


def test_wrong_repository_has_exact_failure(tmp_path: Path) -> None:
    runner = FakeRunner([completed(0, str(tmp_path / "other"))])
    with pytest.raises(SelfHostError) as caught:
        require_repository(tmp_path, runner)
    assert caught.value.code == "PRECHECK_GIT_REPOSITORY_INVALID"


def test_docker_daemon_unavailable_has_actionable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.selfhost.preflight.shutil.which", lambda _name: "docker"
    )
    runner = FakeRunner([completed(0), completed(1)])
    with pytest.raises(SelfHostError) as caught:
        require_tools(runner)
    assert caught.value.code == "PRECHECK_DOCKER_DAEMON_UNAVAILABLE"
    assert "Start Docker" in caught.value.correction


def test_compose_unavailable_is_distinguished(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.selfhost.preflight.shutil.which", lambda _name: "docker"
    )
    runner = FakeRunner([completed(1)])
    with pytest.raises(SelfHostError) as caught:
        require_tools(runner)
    assert caught.value.code == "PRECHECK_COMPOSE_UNAVAILABLE"
