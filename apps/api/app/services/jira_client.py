from __future__ import annotations

import base64
import ipaddress
import json
import socket
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class JiraErrorCode(StrEnum):
    DISABLED = "jira_disabled"
    INVALID_ENDPOINT = "jira_invalid_endpoint"
    AUTHENTICATION_FAILED = "jira_authentication_failed"
    RATE_LIMITED = "jira_rate_limited"
    TRANSIENT_FAILURE = "jira_transient_failure"
    PERMANENT_FAILURE = "jira_permanent_failure"
    INVALID_RESPONSE = "jira_invalid_response"
    TRANSPORT_ERROR = "jira_transport_error"


class JiraClientError(Exception):
    """Raised by JiraClient. Never carries the API token in its message."""

    def __init__(self, code: JiraErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class JiraIssueResult:
    issue_key: str
    issue_url: str


class JiraTransport(Protocol):
    def __call__(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> tuple[int, bytes]: ...


class JiraClient(Protocol):
    def test_connection(self, *, base_url: str, email: str, api_token: str) -> None: ...

    def create_issue(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> JiraIssueResult: ...


def validate_base_url(base_url: str) -> None:
    """SSRF defense: HTTPS only, no embedded credentials, no literal IP host.

    Mirrors app.core.config._validate_provider_endpoint's shape but Jira Cloud
    sites are customer-controlled hostnames (not a fixed allowlist of
    suffixes), so this validates scheme/shape/no-private-IP instead of a
    suffix allowlist.
    """
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
    ):
        raise JiraClientError(
            JiraErrorCode.INVALID_ENDPOINT, "The Jira base URL is not a valid HTTPS endpoint."
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise JiraClientError(
            JiraErrorCode.INVALID_ENDPOINT, "The Jira base URL must not be a literal IP address."
        )
    try:
        resolved = socket.getaddrinfo(host, None)
    except OSError:
        # DNS resolution failure surfaces later as a transport error at call
        # time; do not block configuration on transient resolver issues.
        return
    for _family, _type, _proto, _canon, sockaddr in resolved:
        address = ipaddress.ip_address(sockaddr[0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise JiraClientError(
                JiraErrorCode.INVALID_ENDPOINT,
                "The Jira base URL must not resolve to a private or internal address.",
            )


class RealJiraClient:
    """Jira Cloud REST API v3 adapter over HTTPS-only, bounded-timeout urllib.

    Uses stdlib urllib.request (matching WebhookNotificationProvider) rather
    than adding a new HTTP dependency; httpx is a dev/test-only dependency in
    this repository. The API token is Basic-auth encoded per Jira Cloud's
    documented email+token scheme and is never logged or included in any
    raised error message.
    """

    def __init__(
        self,
        *,
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 15,
        max_retry_attempts: int = 3,
        transport: JiraTransport | None = None,
    ) -> None:
        del connect_timeout_seconds  # urllib exposes a single socket timeout
        self.timeout_seconds = read_timeout_seconds
        self.max_retry_attempts = max_retry_attempts
        self.transport = transport or _urllib_transport

    def test_connection(self, *, base_url: str, email: str, api_token: str) -> None:
        validate_base_url(base_url)
        self._request(
            method="GET",
            url=f"{base_url.rstrip('/')}/rest/api/3/myself",
            email=email,
            api_token=api_token,
            body=None,
        )

    def create_issue(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> JiraIssueResult:
        validate_base_url(base_url)
        payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary[:255],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description[:32_000]}],
                        }
                    ],
                },
                "labels": list(labels or []),
            }
        }
        status, body = self._request(
            method="POST",
            url=f"{base_url.rstrip('/')}/rest/api/3/issue",
            email=email,
            api_token=api_token,
            body=json.dumps(payload).encode(),
        )
        try:
            parsed = json.loads(body)
            issue_key = str(parsed["key"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise JiraClientError(
                JiraErrorCode.INVALID_RESPONSE,
                "Jira returned an invalid issue-creation response.",
            ) from exc
        del status
        return JiraIssueResult(
            issue_key=issue_key,
            issue_url=f"{base_url.rstrip('/')}/browse/{issue_key}",
        )

    def _request(
        self, *, method: str, url: str, email: str, api_token: str, body: bytes | None
    ) -> tuple[int, bytes]:
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CloudOps/1.0",
        }
        last_error: JiraClientError | None = None
        for attempt in range(self.max_retry_attempts):
            try:
                status, response_body = self.transport(
                    method=method,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout_seconds=self.timeout_seconds,
                )
            except (TimeoutError, URLError, OSError) as exc:
                last_error = JiraClientError(
                    JiraErrorCode.TRANSPORT_ERROR,
                    "The connection to Jira failed.",
                    retryable=True,
                )
                if attempt + 1 >= self.max_retry_attempts:
                    raise last_error from exc
                continue
            if 200 <= status < 300:
                return status, response_body
            if status in (401, 403):
                raise JiraClientError(
                    JiraErrorCode.AUTHENTICATION_FAILED,
                    "Jira rejected the configured credentials.",
                )
            if status == 429:
                last_error = JiraClientError(
                    JiraErrorCode.RATE_LIMITED, "Jira rate-limited this request.", retryable=True
                )
                if attempt + 1 >= self.max_retry_attempts:
                    raise last_error
                continue
            if 500 <= status < 600:
                last_error = JiraClientError(
                    JiraErrorCode.TRANSIENT_FAILURE,
                    "Jira returned a transient server error.",
                    retryable=True,
                )
                if attempt + 1 >= self.max_retry_attempts:
                    raise last_error
                continue
            raise JiraClientError(
                JiraErrorCode.PERMANENT_FAILURE,
                "Jira permanently rejected the request.",
            )
        assert last_error is not None  # loop always raises or returns above
        raise last_error


def _urllib_transport(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout_seconds: int,
) -> tuple[int, bytes]:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), response.read(65_536)
    except HTTPError as exc:
        return int(exc.code), exc.read(65_536)


class MockJiraClient:
    """Deterministic, offline Jira client for tests and normal local development."""

    key = "mock"

    def __init__(self, fault_mode: str = "success") -> None:
        self.fault_mode = fault_mode
        self.invocations = 0
        self.created_issues: list[dict[str, object]] = []

    def test_connection(self, *, base_url: str, email: str, api_token: str) -> None:
        del base_url, email, api_token
        self.invocations += 1
        if self.fault_mode == "auth_failure":
            raise JiraClientError(
                JiraErrorCode.AUTHENTICATION_FAILED, "Jira rejected the configured credentials."
            )
        if self.fault_mode == "always_fail":
            raise JiraClientError(
                JiraErrorCode.TRANSIENT_FAILURE, "Mock Jira transient failure.", retryable=True
            )

    def create_issue(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str,
        labels: list[str] | None = None,
    ) -> JiraIssueResult:
        del base_url, email, api_token
        self.invocations += 1
        if self.fault_mode == "auth_failure":
            raise JiraClientError(
                JiraErrorCode.AUTHENTICATION_FAILED, "Jira rejected the configured credentials."
            )
        if self.fault_mode == "always_fail":
            raise JiraClientError(
                JiraErrorCode.TRANSIENT_FAILURE, "Mock Jira transient failure.", retryable=True
            )
        issue_key = f"MOCK-{self.invocations}"
        self.created_issues.append(
            {
                "project_key": project_key,
                "issue_type": issue_type,
                "summary": summary,
                "description": description,
                "labels": list(labels or []),
            }
        )
        return JiraIssueResult(
            issue_key=issue_key, issue_url=f"https://mock.atlassian.net/browse/{issue_key}"
        )
