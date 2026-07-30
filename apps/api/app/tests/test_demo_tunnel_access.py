"""Regression tests for temporary multi-user demo access via one tunnel URL.

The demo is reached through a Cloudflare Quick Tunnel whose hostname is random
and changes on every restart. These tests pin the properties that make that
work without weakening anything:

* a genuinely same-origin request through the tunnel is accepted on the
  cookie-authenticated POST routes, so the ephemeral hostname never has to be
  added to CORS_ALLOWED_ORIGINS or TRUSTED_HOSTS;
* a cross-site Origin is still rejected;
* the allowance is off by default and refused in production-like environments;
* invited users log in separately, keep their own role, and cannot read another
  organization's data.

Nothing here contacts Cloudflare, AWS, or any network service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.tests.conftest import register_and_login

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_DEMO = REPO_ROOT / "compose.demo.yml"
NGINX_CONF = REPO_ROOT / "apps" / "web" / "nginx.conf"
TUNNEL_SCRIPT = REPO_ROOT / "scripts" / "demo_tunnel.ps1"

TUNNEL_ORIGIN = "https://demo-example-tunnel.trycloudflare.com"
TUNNEL_HOST = "demo-example-tunnel.trycloudflare.com"


# --------------------------------------------------------------------------
# Same-origin access through an ephemeral hostname
# --------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "development",
        "database_url": SecretStr("sqlite+pysqlite:///:memory:"),
        "jwt_secret_key": SecretStr("demo-only-jwt-secret-at-least-32-characters"),
    }
    values.update(overrides)
    return Settings(**values)


def test_forwarded_same_origin_allowance_defaults_to_off() -> None:
    assert _settings().trust_forwarded_host_same_origin is False


def test_forwarded_same_origin_allowance_is_refused_in_production() -> None:
    with pytest.raises(ValueError, match="TRUST_FORWARDED_HOST_SAME_ORIGIN"):
        Settings(
            app_env="production",
            database_url=SecretStr("postgresql+psycopg://cloudops:pw@db.invalid/cloudops"),
            jwt_secret_key=SecretStr("production-key-with-at-least-32-characters"),
            cookie_secure=True,
            cors_allowed_origins="https://cloudops.example.invalid",
            trust_forwarded_host_same_origin=True,
        )


def test_forwarded_same_origin_allowance_is_refused_in_staging() -> None:
    with pytest.raises(ValueError, match="TRUST_FORWARDED_HOST_SAME_ORIGIN"):
        Settings(
            app_env="staging",
            database_url=SecretStr("postgresql+psycopg://cloudops:pw@db.invalid/cloudops"),
            jwt_secret_key=SecretStr("staging-key-with-at-least-32-characters"),
            cookie_secure=True,
            cors_allowed_origins="https://cloudops.example.invalid",
            trust_forwarded_host_same_origin=True,
        )


def test_real_app_rejects_a_tunnel_origin_by_default(client: TestClient) -> None:
    """The shipped app has the allowance off, so an unknown Origin is a CSRF block.

    The check runs in middleware, ahead of any authentication.
    """
    response = client.post(
        "/api/v1/auth/refresh",
        headers={
            "Origin": TUNNEL_ORIGIN,
            "X-Forwarded-Host": TUNNEL_HOST,
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 403


def _origin_check_client(
    *, trust_forwarded_host: bool, allowed_origins: set[str] | None = None
) -> TestClient:
    """Minimal app exercising CookieOriginMiddleware.dispatch directly."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from app.logging.middleware import CookieOriginMiddleware

    async def refresh(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    application = Starlette(
        routes=[Route("/api/v1/auth/refresh", refresh, methods=["POST"])]
    )
    application.add_middleware(
        CookieOriginMiddleware,
        allowed_origins=allowed_origins or {"http://localhost:5173"},
        trust_forwarded_host=trust_forwarded_host,
    )
    return TestClient(application)


def _proxy_headers(origin: str, host: str, scheme: str) -> dict[str, str]:
    return {
        "Host": "api",
        "Origin": origin,
        "X-Forwarded-Host": host,
        "X-Forwarded-Proto": scheme,
        "X-CloudOps-Demo-Proxy": "cloudops-demo-nginx",
    }


def test_tunnel_same_origin_request_is_accepted_with_the_allowance() -> None:
    """The whole point: a random tunnel hostname works with no CORS edit."""
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(TUNNEL_ORIGIN, TUNNEL_HOST, "https"),
    )
    assert response.status_code == 200


def test_a_second_tunnel_hostname_also_works_without_configuration_changes() -> None:
    """Restarting the tunnel yields a new hostname; it must work immediately."""
    other_host = "a-completely-different-name.trycloudflare.com"
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(f"https://{other_host}", other_host, "https"),
    )
    assert response.status_code == 200


def test_cross_site_origin_is_still_rejected_with_the_allowance_enabled() -> None:
    """An Origin that is not the browser-facing origin must never be accepted."""
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers("https://evil.example", TUNNEL_HOST, "https"),
    )
    assert response.status_code == 403


def test_scheme_mismatch_is_rejected_with_the_allowance_enabled() -> None:
    """http://host must not satisfy an https://host browser origin."""
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(f"http://{TUNNEL_HOST}", TUNNEL_HOST, "https"),
    )
    assert response.status_code == 403


def test_forged_origin_without_a_forwarded_host_is_rejected() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers={
            "Host": "api",
            "Origin": TUNNEL_ORIGIN,
            "X-Forwarded-Proto": "https",
            "X-CloudOps-Demo-Proxy": "cloudops-demo-nginx",
        },
    )
    assert response.status_code == 403


def test_bogus_forwarded_scheme_cannot_satisfy_the_same_origin_check() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(
            f"javascript://{TUNNEL_HOST}", TUNNEL_HOST, "javascript"
        ),
    )
    assert response.status_code == 403


def test_chained_forwarding_values_are_rejected() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(
            TUNNEL_ORIGIN, f"{TUNNEL_HOST}, internal.invalid", "https"
        ),
    )
    assert response.status_code == 403


def test_matching_localhost_forwarded_origin_is_accepted() -> None:
    response = _origin_check_client(
        trust_forwarded_host=True, allowed_origins={"https://configured.invalid"}
    ).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(
            "http://localhost:5173", "localhost:5173", "http"
        ),
    )
    assert response.status_code == 200


def test_malformed_origin_is_rejected() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(
            f"https://{TUNNEL_HOST}/not-an-origin", TUNNEL_HOST, "https"
        ),
    )
    assert response.status_code == 403


def test_origin_with_malformed_hostname_is_rejected() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers=_proxy_headers(
            "https://bad host.example", "bad host.example", "https"
        ),
    )
    assert response.status_code == 403


def test_direct_client_cannot_spoof_forwarding_headers_without_proxy_marker() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh",
        headers={
            "Origin": TUNNEL_ORIGIN,
            "X-Forwarded-Host": TUNNEL_HOST,
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 403


def test_forwarded_headers_are_rejected_when_internal_host_is_not_api() -> None:
    headers = _proxy_headers(TUNNEL_ORIGIN, TUNNEL_HOST, "https")
    headers["Host"] = "localhost:8000"
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh", headers=headers
    )
    assert response.status_code == 403


def test_allowlisted_localhost_origin_still_works_without_forwarded_headers() -> None:
    response = _origin_check_client(trust_forwarded_host=True).post(
        "/api/v1/auth/refresh", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200


def test_origin_less_client_remains_supported() -> None:
    response = _origin_check_client(trust_forwarded_host=False).post(
        "/api/v1/auth/refresh"
    )
    assert response.status_code == 200


def test_tunnel_origin_is_rejected_when_the_allowance_is_off() -> None:
    response = _origin_check_client(trust_forwarded_host=False).post(
        "/api/v1/auth/refresh",
        headers={
            "Origin": TUNNEL_ORIGIN,
            "X-Forwarded-Host": TUNNEL_HOST,
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Configuration contract
# --------------------------------------------------------------------------


def test_nginx_forwards_browser_facing_host_and_scheme() -> None:
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-Host $http_host;" in content
    assert "proxy_set_header X-Forwarded-Proto $browser_scheme;" in content
    assert "proxy_set_header X-CloudOps-Demo-Proxy cloudops-demo-nginx;" in content
    assert "map $server_port $browser_scheme" in content
    assert "$http_x_forwarded_proto" not in content


def test_compose_demo_adds_no_tunnel_hostname_to_cors_or_trusted_hosts() -> None:
    text = COMPOSE_DEMO.read_text(encoding="utf-8")
    active_lines = [
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ]
    for line in active_lines:
        if "CORS_ALLOWED_ORIGINS:" in line or "TRUSTED_HOSTS:" in line:
            assert "trycloudflare" not in line
    for line in active_lines:
        if "CORS_ALLOWED_ORIGINS:" in line or "TRUSTED_HOSTS:" in line:
            assert "*" not in line


def test_compose_demo_keeps_the_tunnel_behind_an_opt_in_profile() -> None:
    text = COMPOSE_DEMO.read_text(encoding="utf-8")
    assert "cloudflared:" in text
    assert "tunnel --no-autoupdate --url http://web:8081" in text
    # Opt-in: the default local stack must not expose itself publicly.
    cloudflared_block = text.split("cloudflared:", 1)[1]
    assert "profiles:" in cloudflared_block.split("command:", 1)[0]
    assert "- tunnel" in cloudflared_block.split("command:", 1)[0]


def test_tunnel_requires_no_cloudflare_credentials() -> None:
    text = COMPOSE_DEMO.read_text(encoding="utf-8")
    cloudflared_block = text.split("cloudflared:", 1)[1].split("volumes:", 1)[0]
    for forbidden in ("TUNNEL_TOKEN", "CLOUDFLARE_API_TOKEN", "credentials.json", "--token"):
        assert forbidden not in cloudflared_block


def test_tunnel_script_warns_that_the_url_is_temporary() -> None:
    content = TUNNEL_SCRIPT.read_text(encoding="utf-8")
    assert "CHANGES every time the tunnel restarts" in content
    assert "STOPS WORKING" in content
    assert "-Restart" in content
    # Must not promise persistence.
    assert "permanent URL" not in content
    # Must distinguish application roles from AWS IAM.
    assert "NOT an AWS IAM permission" in content


def test_frontend_bundle_never_hardcodes_a_tunnel_hostname() -> None:
    web_dockerfile = (REPO_ROOT / "apps" / "web" / "Dockerfile").read_text(encoding="utf-8")
    assert "trycloudflare" not in web_dockerfile
    client_ts = (
        REPO_ROOT / "apps" / "web" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    assert "trycloudflare" not in client_ts
    # Empty base URL means the browser uses the current page origin.
    assert 'import.meta.env.VITE_API_BASE_URL ?? ""' in client_ts


# --------------------------------------------------------------------------
# Concurrent multi-user isolation through one shared URL
# --------------------------------------------------------------------------


def test_invited_users_log_in_separately_and_keep_distinct_sessions(
    client: TestClient,
) -> None:
    owner = register_and_login(client, email="owner@cloudops-demo.testmail.com")
    analyst = register_and_login(client, email="analyst@cloudops-demo.testmail.com")

    assert owner["Authorization"] != analyst["Authorization"], (
        "Each browser must receive its own access token; no shared session."
    )

    owner_me = client.get("/api/v1/auth/me", headers=owner).json()
    analyst_me = client.get("/api/v1/auth/me", headers=analyst).json()
    assert owner_me["user"]["email"] == "owner@cloudops-demo.testmail.com"
    assert analyst_me["user"]["email"] == "analyst@cloudops-demo.testmail.com"
    assert owner_me["user"]["id"] != analyst_me["user"]["id"]


def test_one_user_cannot_read_another_organization_through_the_shared_url(
    client: TestClient,
) -> None:
    owner = register_and_login(client, email="owner@cloudops-demo.testmail.com")
    other = register_and_login(client, email="outsider@example.com")

    created = client.post(
        "/api/v1/organizations", headers=owner, json={"name": "CloudOps Demo"}
    )
    assert created.status_code == 201, created.text
    organization_id = created.json()["id"]

    # The second user shares the tunnel URL but must not see this tenant.
    probe = client.get(f"/api/v1/organizations/{organization_id}", headers=other)
    assert probe.status_code in {403, 404}

    listed = client.get("/api/v1/organizations", headers=other).json()
    assert all(item["id"] != organization_id for item in listed)


def test_simultaneous_reads_do_not_leak_identity_between_sessions(
    client: TestClient,
) -> None:
    owner = register_and_login(client, email="owner@cloudops-demo.testmail.com")
    analyst = register_and_login(client, email="analyst@cloudops-demo.testmail.com")

    # Interleave requests the way two concurrent browsers would.
    for _ in range(3):
        owner_response = client.get("/api/v1/auth/me", headers=owner).json()
        analyst_response = client.get("/api/v1/auth/me", headers=analyst).json()
        assert owner_response["user"]["email"] == "owner@cloudops-demo.testmail.com"
        assert analyst_response["user"]["email"] == "analyst@cloudops-demo.testmail.com"


def test_missing_or_foreign_token_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        ).status_code
        == 401
    )
