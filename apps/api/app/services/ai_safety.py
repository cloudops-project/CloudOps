from __future__ import annotations

import json
import re
from typing import Any

MAX_STRING = 1000
MAX_ITEMS = 50
_SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\b(bearer|authorization)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(password|secret|token|access[_-]?key)\b\s*[:=]\s*[^\s,;]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_INSTRUCTION_PATTERNS = (
    re.compile(r"(?i)ignore (all|any|the|previous|prior) instructions"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"(?i)you are now"),
    re.compile(r"(?i)developer message"),
)


def redact_text(value: str) -> str:
    bounded = value[:MAX_STRING]
    for pattern in _SECRET_PATTERNS:
        bounded = pattern.sub("[REDACTED]", bounded)
    for pattern in _INSTRUCTION_PATTERNS:
        bounded = pattern.sub("[UNTRUSTED_INSTRUCTION]", bounded)
    return bounded


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            redact_text(str(key))[:100]: sanitize(item, depth=depth + 1)
            for key, item in list(value.items())[:MAX_ITEMS]
            if str(key).casefold()
            not in {
                "password",
                "secret",
                "token",
                "authorization",
                "credentials",
                "access_key",
                "secret_access_key",
                "session_token",
            }
        }
    if isinstance(value, list):
        return [sanitize(item, depth=depth + 1) for item in value[:MAX_ITEMS]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))


def canonical_json(value: Any) -> str:
    return json.dumps(sanitize(value), sort_keys=True, separators=(",", ":"), default=str)
