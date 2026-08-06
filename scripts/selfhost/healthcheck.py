from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from scripts.selfhost.errors import SelfHostError

EXPECTED_MIGRATION_HEAD = "0020_invitation_delivery_state"


@dataclass(frozen=True, slots=True)
class HealthResult:
    component: str
    status: str
    detail: str


def container_health(inspect_json: str, service: str) -> HealthResult:
    try:
        inspected = json.loads(inspect_json)
        state = inspected[0]["State"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise SelfHostError(
            f"HEALTH_{service.upper()}_INSPECT_FAILED",
            f"Container state for {service} could not be read.",
            f"Inspect `cloudops logs {service}` and Docker daemon health.",
        ) from exc
    health = state.get("Health", {}).get("Status")
    status = health or state.get("Status", "unknown")
    return HealthResult(service, status, status)


def assert_healthy(result: HealthResult) -> None:
    if result.status not in {"healthy", "exited"}:
        code = f"HEALTH_{result.component.upper()}_NOT_HEALTHY"
        if result.component == "worker":
            code = "HEALTH_WORKER_HEARTBEAT_STALE"
        elif result.component == "scheduler":
            code = "HEALTH_SCHEDULER_HEARTBEAT_STALE"
        elif result.component == "cloudflared":
            code = "HEALTH_CLOUDFLARE_TUNNEL_DOWN"
        raise SelfHostError(
            code,
            f"{result.component} is {result.status}.",
            f"Inspect `cloudops logs {result.component}` and correct the reported failure.",
        )


def verify_migration(output: str) -> HealthResult:
    if EXPECTED_MIGRATION_HEAD not in output:
        raise SelfHostError(
            "HEALTH_MIGRATION_HEAD_MISMATCH",
            "The database is not at the expected Alembic revision.",
            "Inspect migration logs and run `cloudops verify` after correcting the migration.",
        )
    return HealthResult("migration", "healthy", EXPECTED_MIGRATION_HEAD)


def public_https_health(
    domain: str,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> HealthResult:
    try:
        response = opener(f"https://{domain}/healthz", timeout=10)
        status = int(getattr(response, "status", 0))
    except (OSError, urllib.error.URLError) as exc:
        raise SelfHostError(
            "HEALTH_PUBLIC_URL_UNREACHABLE",
            "The configured public HTTPS URL did not respond.",
            "Verify Cloudflare DNS, tunnel routing to http://web:8080, and tunnel status.",
        ) from exc
    if status != 200:
        raise SelfHostError(
            "HEALTH_PUBLIC_URL_UNREACHABLE",
            f"The public health endpoint returned HTTP {status}.",
            "Verify Cloudflare DNS and the tunnel public-hostname route.",
        )
    return HealthResult("public_url", "healthy", f"https://{domain}")


def wait_until(
    probe: Callable[[], HealthResult],
    *,
    timeout_seconds: float,
    interval_seconds: float = 2,
) -> HealthResult:
    deadline = time.monotonic() + timeout_seconds
    last: SelfHostError | None = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            assert_healthy(result)
            return result
        except SelfHostError as exc:
            last = exc
            time.sleep(interval_seconds)
    if last is not None:
        raise last
    raise SelfHostError(
        "HEALTH_TIMEOUT",
        "A component did not become healthy before the timeout.",
        "Inspect service logs and available host resources.",
    )
