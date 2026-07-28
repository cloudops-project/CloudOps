import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.dependencies.auth import DbSession
from app.exceptions.errors import AppError
from app.schemas.common import HealthResponse

logger = logging.getLogger("cloudops.health")

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Pure liveness: the process is running and able to handle requests.
    Never checks external dependencies, so this never fails due to the
    database or another service being unavailable."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(db: DbSession) -> HealthResponse:
    """Readiness: the process is live AND its required dependencies are
    reachable. A database failure here is reported as 503 (temporarily
    unavailable) rather than a generic 500, so orchestrators can tell
    "app crashed" apart from "app is up but a dependency is down" and
    keep routing traffic away without restarting the container. No
    connection string, driver error, or exception detail is returned to
    the caller; only the exception type is logged server-side."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error(
            "readiness_check_failed",
            extra={"event_name": "readiness.failed", "error_type": type(exc).__name__},
        )
        raise AppError(
            "dependency_unavailable",
            "A required dependency is temporarily unavailable.",
            503,
        ) from None
    return HealthResponse(status="ready")
