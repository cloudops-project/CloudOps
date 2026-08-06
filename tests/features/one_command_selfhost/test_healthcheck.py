from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.app.worker.heartbeat import is_fresh
from scripts.selfhost.errors import SelfHostError
from scripts.selfhost.healthcheck import (
    HealthResult,
    assert_healthy,
    container_health,
    public_https_health,
    verify_migration,
)


def test_worker_heartbeat_freshness_is_bounded(tmp_path: Path) -> None:
    heartbeat = tmp_path / "worker"
    heartbeat.touch()
    modified = heartbeat.stat().st_mtime
    assert is_fresh(heartbeat, 90, now=modified + 89)
    assert not is_fresh(heartbeat, 90, now=modified + 91)


@pytest.mark.parametrize(
    ("component", "code"),
    [
        ("worker", "HEALTH_WORKER_HEARTBEAT_STALE"),
        ("scheduler", "HEALTH_SCHEDULER_HEARTBEAT_STALE"),
        ("cloudflared", "HEALTH_CLOUDFLARE_TUNNEL_DOWN"),
    ],
)
def test_component_failure_has_exact_diagnostic(component: str, code: str) -> None:
    with pytest.raises(SelfHostError) as caught:
        assert_healthy(HealthResult(component, "unhealthy", "unhealthy"))
    assert caught.value.code == code


def test_container_inspection_extracts_health() -> None:
    payload = json.dumps(
        [{"State": {"Status": "running", "Health": {"Status": "healthy"}}}]
    )
    assert container_health(payload, "api").status == "healthy"


def test_wrong_migration_head_is_rejected() -> None:
    with pytest.raises(SelfHostError) as caught:
        verify_migration("0017_old")
    assert caught.value.code == "HEALTH_MIGRATION_HEAD_MISMATCH"


def test_current_migration_head_is_accepted() -> None:
    result = verify_migration("0020_invitation_delivery_state (head)")

    assert result == HealthResult(
        "migration", "healthy", "0020_invitation_delivery_state"
    )


def test_public_url_reports_unreachable_without_leaking_domain() -> None:
    def unavailable(_url: str, **_kwargs: object) -> object:
        raise OSError("synthetic unavailable")

    with pytest.raises(SelfHostError) as caught:
        public_https_health("cloudops.example.test", opener=unavailable)
    assert caught.value.code == "HEALTH_PUBLIC_URL_UNREACHABLE"
    assert "cloudops.example.test" not in str(caught.value)
