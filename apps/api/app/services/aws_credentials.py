from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings
from app.models import AWSAccount


class AWSConnectionFailure(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, repr=False)
class _TemporaryCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expires_at: datetime


@dataclass(repr=False)
class TenantRoleCredentialProvider:
    """Job-scoped STS provider.

    The initial STS client deliberately receives no explicit credential
    arguments, so Boto3 uses ECS/EKS/EC2/Lambda workload identity in
    production and SSO/profile/credential_process locally. Assumed customer
    credentials exist only on this object and are refreshed under a lock.
    """

    account: AWSAccount
    settings: Settings
    sts_client_factory: Callable[..., Any] = boto3.client
    client_factory: Callable[..., Any] = boto3.client
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    _credentials: _TemporaryCredentials | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def client(self, service: str, region: str | None) -> Any:
        credentials = self._current_credentials()
        return self.client_factory(
            service,
            region_name=region,
            config=self.settings.aws_client_config,
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
            aws_session_token=credentials.session_token,
        )

    def validate_account(self) -> str:
        # Every credential generation is verified in _assume_and_verify.
        self._current_credentials()
        return self.account.account_id

    def _current_credentials(self) -> _TemporaryCredentials:
        refresh_before = self.now() + timedelta(
            seconds=self.settings.aws_credential_refresh_window_seconds
        )
        with self._lock:
            if (
                self._credentials is None
                or self._credentials.expires_at <= refresh_before
            ):
                self._credentials = self._assume_and_verify()
            return self._credentials

    def _assume_and_verify(self) -> _TemporaryCredentials:
        role_arn = self._role_arn()
        external_id = self._external_id()
        if role_arn is None:
            raise AWSConnectionFailure("role_arn_missing")
        if external_id is None:
            raise AWSConnectionFailure("external_id_missing")
        try:
            # No credential arguments: use the standard Boto3 provider chain.
            sts = self.sts_client_factory("sts", config=self.settings.aws_client_config)
            response = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=self._session_name(),
                ExternalId=external_id,
                DurationSeconds=self.settings.aws_role_session_duration_seconds,
            )
            raw = response["Credentials"]
            expiration = raw.get("Expiration")
            if not isinstance(expiration, datetime):
                expiration = self.now() + timedelta(
                    seconds=self.settings.aws_role_session_duration_seconds
                )
            elif expiration.tzinfo is None:
                expiration = expiration.replace(tzinfo=UTC)
            credentials = _TemporaryCredentials(
                access_key_id=str(raw["AccessKeyId"]),
                secret_access_key=str(raw["SecretAccessKey"]),
                session_token=str(raw["SessionToken"]),
                expires_at=expiration,
            )
            identity = self.sts_client_factory(
                "sts",
                config=self.settings.aws_client_config,
                aws_access_key_id=credentials.access_key_id,
                aws_secret_access_key=credentials.secret_access_key,
                aws_session_token=credentials.session_token,
            ).get_caller_identity()
            if str(identity["Account"]) != self.account.account_id:
                raise AWSConnectionFailure("caller_account_mismatch")
            return credentials
        except AWSConnectionFailure:
            raise
        except ClientError as exc:
            raise AWSConnectionFailure(_safe_client_error(exc)) from None
        except (BotoCoreError, KeyError, TypeError):
            raise AWSConnectionFailure("sts_validation_failed") from None

    def _role_arn(self) -> str | None:
        return self.account.role_arn

    def _external_id(self) -> str | None:
        return self.account.external_id

    def _session_name(self) -> str:
        return self.settings.aws_role_session_name


@dataclass(repr=False)
class RemediationRoleCredentialProvider(TenantRoleCredentialProvider):
    """Tenant-isolated provider for the separately trusted remediation role."""

    def _role_arn(self) -> str | None:
        return self.account.remediation_role_arn

    def _external_id(self) -> str | None:
        return self.account.remediation_external_id

    def _session_name(self) -> str:
        return f"{self.settings.aws_role_session_name[:48]}-Remediation"


def _safe_client_error(exc: ClientError) -> str:
    code = str(exc.response.get("Error", {}).get("Code", "client_error"))
    safe_code = re.sub(r"[^a-z0-9]+", "_", code.casefold()).strip("_")
    return f"sts_{safe_code or 'client_error'}"
