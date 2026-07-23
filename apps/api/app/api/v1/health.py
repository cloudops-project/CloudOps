from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies.auth import DbSession
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(db: DbSession) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ready")
