from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions.errors import AppError

logger = logging.getLogger("cloudops.errors")


def _payload(
    request: Request, code: str, message: str, details: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": getattr(request.state, "request_id", "unknown"),
            "details": details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, exc.code, exc.message, exc.details),
            headers=(
                {"WWW-Authenticate": "Bearer"}
                if exc.status_code == 401
                else (
                    {"Retry-After": str(exc.retry_after_seconds)}
                    if exc.status_code == 429 and hasattr(exc, "retry_after_seconds")
                    else None
                )
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(request, "validation_error", "Request validation failed.", details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unexpected_error",
            extra={
                "event_name": "request.failed",
                "result": "failed",
                "error_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content=_payload(request, "internal_error", "An unexpected error occurred.", []),
        )
