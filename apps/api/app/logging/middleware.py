from __future__ import annotations

import logging
import time
import uuid

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
    def __init__(self, app: object, allowed_origins: set[str]) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cookie_authenticated_path = request.url.path.endswith(("/auth/refresh", "/auth/logout"))
        if request.method == "POST" and cookie_authenticated_path:
            origin = request.headers.get("origin")
            if origin and origin not in self.allowed_origins:
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
