from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

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


class AuthenticationRateLimitMiddleware(BaseHTTPMiddleware):
    """Single-process Stage 1 guard; use a shared backend before horizontal scaling."""

    def __init__(self, app: object, limit: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limiter = InMemoryRateLimiter(limit)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        limited_paths = ("/auth/register", "/auth/login", "/auth/refresh")
        if request.method == "POST" and request.url.path.endswith(limited_paths):
            address = request.client.host if request.client else "unknown"
            self.limiter.check(f"{address}:{request.url.path}")
        return await call_next(request)
