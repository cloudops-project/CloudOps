from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from scripts.selfhost.errors import SelfHostError

INTERNAL_SECRET_NAMES = (
    "postgres_password",
    "jwt_secret_key",
    "jira_token_encryption_key",
)


def _secure_write(path: Path, value: str, *, replace: bool = False) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        if not path.read_text(encoding="utf-8").strip():
            raise SelfHostError(
                "CONFIG_GENERATED_SECRET_EMPTY",
                f"Generated secret file is empty: {path.name}",
                "Restore the runtime secret directory from backup or run destroy explicitly.",
            )
        return False
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
    return True


def ensure_internal_secrets(runtime_dir: Path) -> dict[str, bool]:
    return {
        "postgres_password": _secure_write(
            runtime_dir / "postgres_password", secrets.token_urlsafe(36)
        ),
        "jwt_secret_key": _secure_write(
            runtime_dir / "jwt_secret_key", secrets.token_urlsafe(64)
        ),
        "jira_token_encryption_key": _secure_write(
            runtime_dir / "jira_token_encryption_key",
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        ),
    }


def require_internal_secrets(runtime_dir: Path) -> None:
    for name in INTERNAL_SECRET_NAMES:
        path = runtime_dir / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise SelfHostError(
                "CONFIG_GENERATED_SECRET_MISSING",
                f"Initialized runtime secret is missing or empty: {name}",
                "Restore .cloudops/runtime from secure backup; do not regenerate in place.",
            )


def store_tunnel_token(runtime_dir: Path, token: str) -> bool:
    target = runtime_dir / "cloudflare_tunnel_token"
    current = target.read_text(encoding="utf-8").strip() if target.exists() else None
    return _secure_write(
        target, token, replace=current is not None and current != token
    )
