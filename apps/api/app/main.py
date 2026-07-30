from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.exceptions.handlers import register_exception_handlers
from app.logging.config import configure_logging
from app.logging.middleware import (
    AuthenticationRateLimitMiddleware,
    CookieOriginMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.security.trusted_host import HealthCheckTrustedHostMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name, version="1.0.0")
    application.add_middleware(
        SecurityHeadersMiddleware, hsts_enabled=settings.hsts_enabled
    )
    application.add_middleware(
        HealthCheckTrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.add_middleware(
        CookieOriginMiddleware,
        allowed_origins=set(settings.allowed_origins),
        trust_forwarded_host=settings.trust_forwarded_host_same_origin,
    )
    application.add_middleware(
        AuthenticationRateLimitMiddleware,
        limit=(10000 if settings.app_env == "testing" else settings.auth_rate_limit_per_minute),
    )
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
