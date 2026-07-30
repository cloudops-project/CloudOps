from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class SecretBoxError(Exception):
    """Raised when a value cannot be encrypted or decrypted at rest."""


def load_key(encoded_key: str) -> bytes:
    """Decode a base64/url-safe-base64 32-byte AES-256-GCM key.

    This is an application-level stopgap: the decoded bytes are the actual
    encryption key material. Production deployments must source
    ``encoded_key`` from a KMS-backed secret store (e.g. AWS Secrets Manager
    with envelope encryption), not a static environment variable committed
    anywhere. Raises SecretBoxError if the key is missing or not exactly
    32 bytes once decoded.
    """
    if not encoded_key:
        raise SecretBoxError("A Jira token encryption key is not configured.")
    padded = encoded_key + "=" * (-len(encoded_key) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except (ValueError, TypeError) as exc:
        raise SecretBoxError("The Jira token encryption key is not valid base64.") from exc
    if len(raw) != KEY_BYTES:
        raise SecretBoxError(
            f"The Jira token encryption key must decode to exactly {KEY_BYTES} bytes."
        )
    return raw


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt with AES-256-GCM. Returns url-safe-base64(nonce || ciphertext || tag)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(token: str, key: bytes) -> str:
    """Inverse of encrypt(). Raises SecretBoxError on any tampering or key mismatch."""
    try:
        raw = base64.urlsafe_b64decode(token.encode())
    except (ValueError, TypeError) as exc:
        raise SecretBoxError("The stored secret is not valid base64.") from exc
    if len(raw) <= NONCE_BYTES:
        raise SecretBoxError("The stored secret is truncated.")
    nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise SecretBoxError("The stored secret could not be decrypted.") from exc
    return plaintext.decode()
