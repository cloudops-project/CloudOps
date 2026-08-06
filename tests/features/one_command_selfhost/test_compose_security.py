from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (ROOT / "compose.selfhost.yml").read_text(encoding="utf-8")


def service_block(name: str, next_name: str | None) -> str:
    start = COMPOSE.index(f"  {name}:")
    end = COMPOSE.index(f"\n  {next_name}:", start) if next_name else len(COMPOSE)
    return COMPOSE[start:end]


def test_database_and_api_have_no_published_ports() -> None:
    assert "ports:" not in service_block("postgres", "migration")
    assert "ports:" not in service_block("api", "worker")


def test_cloudflared_can_reach_only_tunnel_network() -> None:
    block = service_block("cloudflared", None).split("\nvolumes:", 1)[0]
    assert "      - tunnel" in block
    assert "backend" not in block
    assert "egress" not in block


def test_web_is_only_bridge_between_tunnel_and_backend() -> None:
    block = service_block("web", "cloudflared")
    assert "      - backend" in block
    assert "      - tunnel" in block


def test_migration_gates_application_services() -> None:
    assert "condition: service_completed_successfully" in service_block("api", "worker")
    assert "0020_invitation_delivery_state" in service_block("migration", "api")


def test_required_restart_health_volume_and_security_controls_exist() -> None:
    assert COMPOSE.count("restart: unless-stopped") >= 6
    assert COMPOSE.count("healthcheck:") >= 5
    assert "cloudops_postgres:/var/lib/postgresql/data" in COMPOSE
    assert "internal: true" in COMPOSE
    assert "no-new-privileges:true" in COMPOSE
    assert "cap_drop:" in COMPOSE


def test_organization_stack_has_no_demo_or_mailpit_service() -> None:
    assert "\n  mailpit:" not in COMPOSE
    assert 'DEMO_SYNTHETIC_DISCOVERY: "false"' in COMPOSE
    assert 'REMEDIATION_LIVE_AWS_ENABLED: "false"' in COMPOSE


def test_cloudflare_token_uses_file_secret() -> None:
    block = service_block("cloudflared", None)
    assert "cloudflare_tunnel_token" in block
    assert "CLOUDFLARE_TUNNEL_TOKEN" not in block
    dockerfile = (ROOT / "scripts/selfhost/cloudflared.Dockerfile").read_text(
        encoding="utf-8"
    )
    entrypoint = (ROOT / "scripts/selfhost/cloudflared-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "cloudflare/cloudflared:2024.12.2" in dockerfile
    assert "adduser -S -u 10001" in dockerfile
    assert 'TUNNEL_TOKEN="$(cat "${token_path}")"' in entrypoint
    assert "exec su-exec cloudops cloudflared" in entrypoint
    assert "tunnel run" in entrypoint


def test_secret_bootstrap_drops_to_fixed_non_root_uid() -> None:
    api_dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    api_entrypoint = (ROOT / "scripts/selfhost/container_env.sh").read_text(encoding="utf-8")
    assert "adduser -S -u 10001" in api_dockerfile
    assert 'exec su-exec cloudops "$@"' in api_entrypoint
    assert 'user: "0:0"' in COMPOSE
    assert "DAC_OVERRIDE" in service_block("cloudflared", None)


def _cloudflared_capabilities() -> tuple[list[str], list[str]]:
    """Parse the cloudflared cap_drop and cap_add lists from the compose file."""
    block = service_block("cloudflared", None).split("\nvolumes:", 1)[0]
    dropped: list[str] = []
    added: list[str] = []
    target: list[str] | None = None
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line == "cap_drop:":
            target = dropped
            continue
        if line == "cap_add:":
            target = added
            continue
        if line.startswith("- ") and target is not None:
            target.append(line[2:].strip())
            continue
        if line and not line.startswith("#") and not line.startswith("- "):
            target = None
    return dropped, added


def test_cloudflared_drops_all_capabilities() -> None:
    dropped, _ = _cloudflared_capabilities()
    assert dropped == ["ALL"]


def test_cloudflared_adds_exactly_the_su_exec_transition_capabilities() -> None:
    """su-exec needs SETGID/SETUID for setgroups(2)/setgid(2)/setuid(2) and
    DAC_OVERRIDE to read the 0600 tunnel-token secret. Nothing else may be
    granted: a broader list reintroduces privilege this service must not hold."""
    _, added = _cloudflared_capabilities()
    assert sorted(added) == ["DAC_OVERRIDE", "SETGID", "SETUID"]


def test_cloudflared_rejects_broader_privilege() -> None:
    _, added = _cloudflared_capabilities()
    forbidden = {
        "ALL",
        "SYS_ADMIN",
        "NET_ADMIN",
        "NET_RAW",
        "SYS_PTRACE",
        "SYS_MODULE",
        "DAC_READ_SEARCH",
        "SETPCAP",
        "CHOWN",
        "FOWNER",
    }
    assert not forbidden.intersection(added)


def test_cloudflared_is_not_privileged_and_keeps_hardening() -> None:
    block = service_block("cloudflared", None).split("\nvolumes:", 1)[0]
    assert "privileged: true" not in block
    assert "privileged:" not in block
    assert "no-new-privileges:true" in block
    assert "read_only: true" in block


def test_cloudflared_token_remains_a_docker_secret_after_capability_change() -> None:
    block = service_block("cloudflared", None).split("\nvolumes:", 1)[0]
    assert "      - cloudflare_tunnel_token" in block
    assert "CLOUDFLARE_TUNNEL_TOKEN" not in block
    assert "TUNNEL_TOKEN" not in block
