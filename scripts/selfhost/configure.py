from __future__ import annotations

import os
import re
from getpass import getpass
from pathlib import Path

from scripts.selfhost.errors import SelfHostError
from scripts.selfhost.generate_secrets import (
    ensure_internal_secrets,
    require_internal_secrets,
    store_tunnel_token,
)

DEFAULTS = {
    "APP_ENV": "production",
    "POSTGRES_DB": "cloudops",
    "POSTGRES_USER": "cloudops",
    "AWS_REGION": "us-east-1",
    "AI_PROVIDER": "mock",
    "NOTIFICATION_PROVIDER": "mock",
    "JIRA_ENABLED": "false",
    "AWS_BEDROCK_ENABLED": "false",
    "AWS_SES_ENABLED": "false",
    "REMEDIATION_EXECUTION_ENABLED": "false",
    "REMEDIATION_LIVE_AWS_ENABLED": "false",
    "CLOUDOPS_INITIALIZED": "false",
}
REQUIRED = ("CLOUDOPS_DOMAIN", "CLOUDFLARE_TUNNEL_TOKEN")
DOMAIN_RE = re.compile(
    r"(?=^.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SelfHostError(
                "CONFIG_ENV_MALFORMED",
                f"Configuration line {number} is not KEY=VALUE.",
                f"Correct {path.name} and rerun.",
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise SelfHostError(
                "CONFIG_ENV_MALFORMED",
                f"Configuration line {number} has an invalid key.",
                f"Correct {path.name} and rerun.",
            )
        if value.startswith(("'", '"')) and value[-1:] == value[:1]:
            value = value[1:-1]
        if any(character in value for character in ("\x00", "\n", "\r")):
            raise SelfHostError(
                "CONFIG_ENV_MALFORMED",
                f"Configuration line {number} contains a forbidden control character.",
                f"Correct {path.name} and rerun.",
            )
        values[key] = value
    return values


def _validate_domain(value: str) -> str:
    domain = value.strip().casefold().rstrip(".")
    if (
        "://" in domain
        or "/" in domain
        or "*" in domain
        or not DOMAIN_RE.fullmatch(domain)
    ):
        raise SelfHostError(
            "CONFIG_CLOUDFLARE_DOMAIN_INVALID",
            "CLOUDOPS_DOMAIN must be a valid DNS hostname without a scheme, path, or wildcard.",
            "Use a hostname such as cloudops.example.com.",
        )
    return domain


def validate(values: dict[str, str]) -> dict[str, str]:
    result = DEFAULTS | values
    if result["APP_ENV"] != "production":
        raise SelfHostError(
            "CONFIG_PRODUCTION_ENV_REQUIRED",
            "Organization self-hosting requires APP_ENV=production.",
            "Set APP_ENV=production. Use `demo-up` for synthetic development mode.",
        )
    if not result.get("CLOUDOPS_DOMAIN"):
        raise SelfHostError(
            "CONFIG_CLOUDFLARE_DOMAIN_MISSING",
            "CLOUDOPS_DOMAIN is required.",
            "Set the hostname routed by the named Cloudflare Tunnel.",
        )
    result["CLOUDOPS_DOMAIN"] = _validate_domain(result["CLOUDOPS_DOMAIN"])
    token = result.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    if len(token) < 20 or token.casefold() in {"replace-me", "changeme", "placeholder"}:
        raise SelfHostError(
            "CONFIG_CLOUDFLARE_TOKEN_MISSING",
            "A non-placeholder Cloudflare Tunnel token is required.",
            "Create a named tunnel, copy its token into .env.selfhost, and rerun.",
        )
    if (
        not result.get("POSTGRES_DB", "").strip()
        or not result.get("POSTGRES_USER", "").strip()
    ):
        raise SelfHostError(
            "CONFIG_DATABASE_IDENTITY_MISSING",
            "POSTGRES_DB and POSTGRES_USER must be non-empty.",
            "Set non-secret database identifiers in .env.selfhost.",
        )
    for key in (
        "DEMO_SYNTHETIC_DISCOVERY",
        "TRUST_FORWARDED_HOST_SAME_ORIGIN",
        "REMEDIATION_LIVE_AWS_ENABLED",
    ):
        if result.get(key, "false").casefold() in {"1", "true", "yes", "on"}:
            raise SelfHostError(
                "CONFIG_PRODUCTION_UNSAFE_SETTING",
                f"{key} is forbidden in organization mode.",
                "Remove the development/live-mutation setting and rerun.",
            )
    if result["CLOUDOPS_INITIALIZED"].casefold() not in {"true", "false"}:
        raise SelfHostError(
            "CONFIG_INITIALIZATION_STATE_INVALID",
            "CLOUDOPS_INITIALIZED must be true or false.",
            "Restore the generated configuration; use false only for a genuine first install.",
        )
    return result


def write_env(path: Path, values: dict[str, str]) -> None:
    ordered = ("CLOUDOPS_DOMAIN", "CLOUDFLARE_TUNNEL_TOKEN", *DEFAULTS.keys())
    lines = [
        "# Local CloudOps self-host configuration. Never commit this file.",
        *(f"{key}={values[key]}" for key in ordered),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def configure(
    root: Path,
    *,
    interactive: bool,
    environment: dict[str, str] | None = None,
) -> dict[str, str]:
    config_path = root / ".env.selfhost"
    existing = read_env(config_path)
    supplied = environment if environment is not None else dict(os.environ)
    values = DEFAULTS | existing
    for key in REQUIRED:
        if supplied.get(key):
            values[key] = supplied[key]
        if not values.get(key) and interactive:
            if key == "CLOUDOPS_DOMAIN":
                values[key] = input("CloudOps domain: ").strip()
            else:
                values[key] = getpass("Cloudflare Tunnel token (hidden): ").strip()
    values = validate(values)
    runtime_dir = root / ".cloudops" / "runtime"
    if values["CLOUDOPS_INITIALIZED"].casefold() == "true":
        require_internal_secrets(runtime_dir)
    else:
        ensure_internal_secrets(runtime_dir)
        values["CLOUDOPS_INITIALIZED"] = "true"
    store_tunnel_token(runtime_dir, values["CLOUDFLARE_TUNNEL_TOKEN"])
    write_env(config_path, values)
    return values
