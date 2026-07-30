from __future__ import annotations

import ipaddress
import logging
import time
import uuid
from urllib.parse import urlsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.exceptions.errors import RateLimitError
from app.logging.config import request_id_context
from app.security.rate_limit import InMemoryRateLimiter

logger = logging.getLogger("cloudops.requests")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied[:128] if supplied and supplied.isascii() else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request.completed",
                extra={
                    "event_name": "request.completed",
                    "result": "succeeded" if response.status_code < 400 else "failed",
                    "user_id": getattr(request.state, "user_id", None),
                    "organization_id": getattr(request.state, "organization_id", None),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return response
        finally:
            request_id_context.reset(token)


class CookieOriginMiddleware(BaseHTTPMiddleware):
    """CSRF guard for the two cookie-authenticated POST routes.

    An Origin that is present but not allowlisted is rejected. Origin-less
    non-browser clients remain supported.

    ``trust_forwarded_host`` additionally accepts an Origin whose scheme, host
    and port match the origin the browser actually used to reach the app, as
    reported by ``X-Forwarded-Host``/``X-Forwarded-Proto`` from the reverse
    proxy. That is genuinely same-origin, so it is not a CSRF risk, and it lets
    a same-origin deployment behind an ephemeral public hostname (the demo's
    Cloudflare Quick Tunnel) work without editing the CORS allowlist whenever
    the hostname changes.

    It is off by default and Settings refuses it in production-like
    environments, because ``X-Forwarded-*`` is only trustworthy when every
    request path terminates at a trusted proxy. With it off, behaviour is
    byte-identical to the allowlist-only check.
    """

    def __init__(
        self,
        app: object,
        allowed_origins: set[str],
        *,
        trust_forwarded_host: bool = False,
        trusted_proxy_marker: str = "cloudops-demo-nginx",
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed_origins = allowed_origins
        self.trust_forwarded_host = trust_forwarded_host
        self.trusted_proxy_marker = trusted_proxy_marker

    @staticmethod
    def _canonical_origin(value: str) -> str | None:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        host = parsed.hostname.casefold()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if any(
                not label
                or len(label) > 63
                or label[0] == "-"
                or label[-1] == "-"
                or not all(character.isalnum() or character == "-" for character in label)
                for label in labels
            ):
                return None
        if ":" in host:
            host = f"[{host}]"
        default_port = 80 if parsed.scheme == "http" else 443
        authority = host if port in {None, default_port} else f"{host}:{port}"
        return f"{parsed.scheme}://{authority}"

    def _forwarded_origin(self, request: Request) -> str | None:
        if (
            request.headers.get("x-cloudops-demo-proxy") != self.trusted_proxy_marker
            or request.headers.get("host", "").casefold() != "api"
        ):
            return None
        forwarded_host = request.headers.get("x-forwarded-host", "").strip()
        scheme = request.headers.get("x-forwarded-proto", "").strip()
        if (
            not forwarded_host
            or "," in forwarded_host
            or scheme not in {"http", "https"}
        ):
            return None
        return self._canonical_origin(f"{scheme}://{forwarded_host}")

    def _is_forwarded_same_origin(self, request: Request, origin: str) -> bool:
        return (
            self.trust_forwarded_host
            and self._canonical_origin(origin) is not None
            and self._canonical_origin(origin) == self._forwarded_origin(request)
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cookie_authenticated_path = request.url.path.endswith(("/auth/refresh", "/auth/logout"))
        if request.method == "POST" and cookie_authenticated_path:
            origin = request.headers.get("origin")
            if (
                origin
                and origin not in self.allowed_origins
                and not self._is_forwarded_same_origin(request, origin)
            ):
                return Response(status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies code-level HTTP security headers appropriate for a JSON API
    backend (no server-rendered HTML, so the CSP can stay maximally strict).
    TLS termination, HSTS preload-list submission, and any WAF/CDN-level
    headers remain infrastructure/deployment responsibilities."""

    def __init__(self, app: object, *, hsts_enabled: bool) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # This API never renders HTML and is not meant to be framed; deny
        # both via CSP frame-ancestors and the legacy X-Frame-Options header.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        if "/auth/" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
        if self.hsts_enabled:
            # HSTS is gated by an explicit deployment guarantee rather than
            # APP_ENV alone; see Settings.model_post_init.
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        return response


class AuthenticationRateLimitMiddleware(BaseHTTPMiddleware):
    """Single-process Stage 1 guard; use a shared backend before horizontal scaling."""

    def __init__(self, app: object, limit: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limiter = InMemoryRateLimiter(limit)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        limited_paths = ("/auth/register", "/auth/login", "/auth/refresh")
        if request.method == "POST" and request.url.path.endswith(limited_paths):
            address = request.client.host if request.client else "unknown"
            try:
                self.limiter.check(f"{address}:{request.url.path}")
            except RateLimitError as exc:
                request_id = getattr(request.state, "request_id", "unknown")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "correlation_id": request_id,
                            "details": exc.details,
                        }
                    },
                    headers={"Retry-After": str(exc.retry_after_seconds)},
                )
        return await call_next(request)
