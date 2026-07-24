from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


class AuthenticationError(AppError):
    def __init__(
        self, code: str = "invalid_authentication", message: str = "Authentication required."
    ) -> None:
        super().__init__(code, message, 401)


class ForbiddenError(AppError):
    def __init__(
        self,
        code: str = "forbidden",
        message: str = "You do not have permission to perform this action.",
    ) -> None:
        super().__init__(code, message, 403)


class NotFoundError(AppError):
    def __init__(
        self, code: str = "not_found", message: str = "The requested resource was not found."
    ) -> None:
        super().__init__(code, message, 404)


class ConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class RateLimitError(AppError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after_seconds: int,
        limit: int,
        current_usage: int,
    ) -> None:
        super().__init__(
            code,
            message,
            429,
            [
                {
                    "retry_after_seconds": retry_after_seconds,
                    "limit": limit,
                    "current_usage": current_usage,
                }
            ],
        )
        self.retry_after_seconds = retry_after_seconds
