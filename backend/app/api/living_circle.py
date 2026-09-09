from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.living_circle import LivingCircleRequest, LivingCircleResponse
from app.services.living_circle import (
    LivingCircleGeometryError,
    PedestrianNetworkUnavailableError,
    PedestrianSnapNotFoundError,
    PoiWalkAccessUnavailableError,
    analyze_living_circle,
)

router = APIRouter(prefix="/api/v1/living-circle", tags=["living-circle"])


@router.post("/analyze", response_model=LivingCircleResponse)
def living_circle_analyze(
    request: LivingCircleRequest,
    db: Session = Depends(get_db),
) -> LivingCircleResponse:
    try:
        return analyze_living_circle(
            db, origin=request.origin, max_snap_m=request.max_snap_m
        )
    except PedestrianSnapNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PoiWalkAccessUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PedestrianNetworkUnavailableError, LivingCircleGeometryError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Living-circle analysis failed") from exc
