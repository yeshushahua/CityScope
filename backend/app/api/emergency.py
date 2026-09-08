from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.emergency import EmergencyResponse, EmergencyResponseRequest
from app.services.emergency import analyze_emergency_response
from app.services.routing import (
    FacilityNotFoundError,
    IsochroneGeometryError,
    ReachableFacilityNotFoundError,
    RouteNotFoundError,
    SnapNotFoundError,
)

router = APIRouter(prefix="/api/v1/emergency", tags=["emergency"])


@router.post("/response", response_model=EmergencyResponse)
def emergency_response(
    request: EmergencyResponseRequest,
    db: Session = Depends(get_db),
) -> EmergencyResponse:
    try:
        return analyze_emergency_response(
            db,
            incident=request.incident,
            incident_type=request.incident_type,
            max_snap_m=request.max_snap_m,
            candidate_limit=request.candidate_limit,
        )
    except SnapNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FacilityNotFoundError, ReachableFacilityNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RouteNotFoundError, IsochroneGeometryError) as exc:
        raise HTTPException(status_code=503, detail="Emergency analysis failed") from exc
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Emergency analysis failed") from exc
