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
    assert "0018_jira_integration" in service_block("migration", "api")


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
