from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/database", response_model=DatabaseHealthResponse)
def database_health(
    response: Response,
    db: Session = Depends(get_db),
) -> DatabaseHealthResponse:
    try:
        db.execute(text("SELECT 1"))
        postgis_enabled = bool(
            db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')"))
        )
        if not postgis_enabled:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return DatabaseHealthResponse(
                status="error",
                database="PostgreSQL",
                postgis=False,
                detail="PostGIS extension is not enabled",
            )
        return DatabaseHealthResponse(status="ok", database="PostgreSQL", postgis=True)
    except SQLAlchemyError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DatabaseHealthResponse(
            status="error",
            database="PostgreSQL",
            postgis=False,
            detail=f"Database connection failed: {exc.__class__.__name__}",
        )
