from __future__ import annotations

from pathlib import Path

import pytest

from scripts.selfhost.configure import configure, validate
from scripts.selfhost.errors import SelfHostError
from scripts.selfhost.generate_secrets import ensure_internal_secrets


def values(**overrides: str) -> dict[str, str]:
    return {
        "CLOUDOPS_DOMAIN": "cloudops.example.test",
        "CLOUDFLARE_TUNNEL_TOKEN": "synthetic-test-token-not-a-real-token",
        **overrides,
    }


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"CLOUDOPS_DOMAIN": ""}, "CONFIG_CLOUDFLARE_DOMAIN_MISSING"),
        (
            {"CLOUDOPS_DOMAIN": "https://bad.example.test"},
            "CONFIG_CLOUDFLARE_DOMAIN_INVALID",
        ),
        ({"CLOUDOPS_DOMAIN": "*.example.test"}, "CONFIG_CLOUDFLARE_DOMAIN_INVALID"),
        ({"CLOUDFLARE_TUNNEL_TOKEN": ""}, "CONFIG_CLOUDFLARE_TOKEN_MISSING"),
        ({"APP_ENV": "development"}, "CONFIG_PRODUCTION_ENV_REQUIRED"),
        ({"DEMO_SYNTHETIC_DISCOVERY": "true"}, "CONFIG_PRODUCTION_UNSAFE_SETTING"),
        (
            {"TRUST_FORWARDED_HOST_SAME_ORIGIN": "true"},
            "CONFIG_PRODUCTION_UNSAFE_SETTING",
        ),
        ({"REMEDIATION_LIVE_AWS_ENABLED": "true"}, "CONFIG_PRODUCTION_UNSAFE_SETTING"),
    ],
)
def test_unsafe_configuration_reports_exact_code(
    overrides: dict[str, str], code: str
) -> None:
    with pytest.raises(SelfHostError, match=code) as caught:
        validate(values(**overrides))
    assert caught.value.code == code
    assert caught.value.correction


def test_configure_writes_runtime_secrets_without_echoing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = configure(tmp_path, interactive=False, environment=values())
    assert result["CLOUDOPS_DOMAIN"] == "cloudops.example.test"
    assert result["CLOUDOPS_INITIALIZED"] == "true"
    runtime = tmp_path / ".cloudops" / "runtime"
    assert {item.name for item in runtime.iterdir()} == {
        "postgres_password",
        "jwt_secret_key",
        "jira_token_encryption_key",
        "cloudflare_tunnel_token",
    }
    assert result["CLOUDFLARE_TUNNEL_TOKEN"] not in capsys.readouterr().out


def test_secret_generation_preserves_existing_values(tmp_path: Path) -> None:
    first = ensure_internal_secrets(tmp_path)
    originals = {
        path.name: path.read_text(encoding="utf-8") for path in tmp_path.iterdir()
    }
    second = ensure_internal_secrets(tmp_path)
    assert all(first.values())
    assert not any(second.values())
    assert originals == {
        path.name: path.read_text(encoding="utf-8") for path in tmp_path.iterdir()
    }


def test_empty_generated_secret_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "jwt_secret_key").write_text("", encoding="utf-8")
    with pytest.raises(SelfHostError) as caught:
        ensure_internal_secrets(tmp_path)
    assert caught.value.code == "CONFIG_GENERATED_SECRET_EMPTY"


def test_initialized_install_refuses_to_regenerate_missing_secret(tmp_path: Path) -> None:
    configure(tmp_path, interactive=False, environment=values())
    (tmp_path / ".cloudops" / "runtime" / "jwt_secret_key").unlink()
    with pytest.raises(SelfHostError) as caught:
        configure(tmp_path, interactive=False, environment=values())
    assert caught.value.code == "CONFIG_GENERATED_SECRET_MISSING"


def test_interactive_token_prompt_is_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "cloudops.example.test")
    prompts: list[str] = []

    def hidden(prompt: str) -> str:
        prompts.append(prompt)
        return "synthetic-test-token-not-a-real-token"

    monkeypatch.setattr("scripts.selfhost.configure.getpass", hidden)
    configure(tmp_path, interactive=True, environment={})
    assert prompts == ["Cloudflare Tunnel token (hidden): "]
